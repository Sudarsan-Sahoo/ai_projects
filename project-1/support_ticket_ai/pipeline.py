from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from support_ticket_ai.evaluation import (
    parse_reply_evaluation_output,
    parse_summary_evaluation_output,
)
from support_ticket_ai.paths import outputs_dir
from support_ticket_ai.prompts import (
    REPLY_EVAL_SYSTEM_PROMPT,
    REPLY_SYSTEM_PROMPT,
    SUMMARY_EVAL_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
)


@dataclass(frozen=True)
class PipelinePaths:
    data_csv: Path
    out_dir: Path


def _pick_ticket_column(df: pd.DataFrame) -> str:
    if "support_ticket_text" in df.columns:
        return "support_ticket_text"
    if "support_ticket_desc" in df.columns:
        return "support_ticket_desc"
    raise ValueError(
        "Input CSV must contain either `support_ticket_text` or `support_ticket_desc`."
    )


def load_tickets(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if "support_ticket_id" not in df.columns:
        raise ValueError("Input CSV must contain `support_ticket_id`.")
    return df


def offline_report(final_outputs_csv: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(final_outputs_csv)

    metrics = {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
    }

    def mean_if_present(col: str) -> float | None:
        return float(df[col].dropna().mean()) if col in df.columns else None

    summary_means = {
        "summary_clarity": mean_if_present("summary_clarity"),
        "summary_coverage": mean_if_present("summary_coverage"),
        "summary_faithfulness": mean_if_present("summary_faithfulness"),
    }
    response_means = {
        "response_relevance": mean_if_present("response_relevance"),
        "response_empathy_tone": mean_if_present("response_empathy_tone"),
        "response_accuracy_safety": mean_if_present("response_accuracy_safety"),
        "response_actionability": mean_if_present("response_actionability"),
        "response_clarity": mean_if_present("response_clarity"),
    }

    report_path = out_dir / "offline_report.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Offline Run Report\n\n")
        f.write("This project is configured to run offline by default.\n\n")
        f.write("## Dataset\n")
        f.write(f"- Rows: {metrics['rows']}\n")
        f.write(f"- Columns: {metrics['columns']}\n\n")

        if any(v is not None for v in summary_means.values()):
            f.write("## Summary Evaluation (Mean)\n")
            for k, v in summary_means.items():
                if v is not None:
                    f.write(f"- {k}: {v:.2f}\n")
            f.write("\n")

        if any(v is not None for v in response_means.values()):
            f.write("## Reply Evaluation (Mean)\n")
            for k, v in response_means.items():
                if v is not None:
                    f.write(f"- {k}: {v:.2f}\n")
            f.write("\n")

        preview_cols = [
            c
            for c in [
                "support_ticket_id",
                "raw_ticket_text",
                "generated_summary",
                "generated_response",
            ]
            if c in df.columns
        ]
        if preview_cols:
            f.write("## Preview (First 3 Rows)\n\n")
            f.write("```text\n")
            f.write(df[preview_cols].head(3).to_string(index=False))
            f.write("\n```\n")

    return report_path


def run_offline(out_dir: Path | None = None) -> Path:
    out_dir = out_dir or outputs_dir()
    final_csv = out_dir / "final_consolidated_ticket_outputs.csv"
    if not final_csv.exists():
        raise FileNotFoundError(
            f"Missing offline outputs at `{final_csv}`. "
            "Expected `outputs/final_consolidated_ticket_outputs.csv`."
        )
    return offline_report(final_outputs_csv=final_csv, out_dir=out_dir)


def run_online(
    paths: PipelinePaths,
    *,
    limit: int | None = None,
    summary_model: str = "gpt-4o-mini",
    eval_model: str = "gpt-4o",
    reply_model: str = "gpt-4o",
) -> dict[str, Path]:
    """
    Runs the full pipeline (requires API credentials in env vars).
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    paths.out_dir.mkdir(parents=True, exist_ok=True)

    df = load_tickets(paths.data_csv)
    ticket_col = _pick_ticket_column(df)
    if limit is not None:
        df = df.head(limit).copy()

    # --- Summaries ---
    summary_llm = ChatOpenAI(model_name=summary_model).bind(
        temperature=0.1,
        max_tokens=300,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
    )
    summaries: list[str] = []
    for ticket_text in df[ticket_col].fillna("").tolist():
        resp = summary_llm.invoke(
            [SystemMessage(content=SUMMARY_SYSTEM_PROMPT), HumanMessage(content=ticket_text)]
        )
        summaries.append(resp.content)

    summary_df = df.copy()
    summary_df["generated_summary"] = summaries
    summary_df_full = summary_df[["support_ticket_id", ticket_col, "generated_summary"]].copy()

    # --- Evaluate summaries ---
    eval_llm = ChatOpenAI(model_name=eval_model, temperature=0.1, top_p=0.9)
    eval_rows: list[dict] = []
    for _, row in summary_df_full.iterrows():
        resp = eval_llm.invoke(
            [
                SystemMessage(content=SUMMARY_EVAL_SYSTEM_PROMPT),
                HumanMessage(content=f"Ticket summary:\n{row['generated_summary']}"),
            ]
        )
        parsed = parse_summary_evaluation_output(resp.content)
        parsed["support_ticket_id"] = row["support_ticket_id"]
        eval_rows.append(parsed)
    summary_eval_df = pd.DataFrame(eval_rows)
    summary_df_full = summary_df_full.merge(summary_eval_df, on="support_ticket_id", how="left")

    # --- Replies ---
    reply_llm = ChatOpenAI(model_name=reply_model).bind(
        temperature=0.35,
        max_tokens=280,
        top_p=0.9,
        frequency_penalty=0.1,
        presence_penalty=0.05,
    )
    replies: list[str] = []
    for _, row in summary_df_full.iterrows():
        resp = reply_llm.invoke(
            [
                SystemMessage(content=REPLY_SYSTEM_PROMPT),
                HumanMessage(content=f"Ticket summary:\n{row['generated_summary']}"),
            ]
        )
        replies.append(resp.content.strip())
    response_df = pd.DataFrame(
        {"support_ticket_id": summary_df_full["support_ticket_id"], "generated_response": replies}
    )

    # --- Evaluate replies ---
    reply_eval_llm = ChatOpenAI(model_name=eval_model, temperature=0.1, max_tokens=280)
    reply_eval_input_df = summary_df_full[["support_ticket_id", "generated_summary"]].merge(
        response_df, on="support_ticket_id", how="inner"
    )
    reply_eval_rows: list[dict] = []
    for _, row in reply_eval_input_df.iterrows():
        resp = reply_eval_llm.invoke(
            [
                SystemMessage(content=REPLY_EVAL_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Ticket summary:\n{row['generated_summary']}\n\n"
                        f"Generated customer reply:\n{row['generated_response']}"
                    )
                ),
            ]
        )
        parsed = parse_reply_evaluation_output(resp.content)
        parsed["support_ticket_id"] = row["support_ticket_id"]
        reply_eval_rows.append(parsed)
    reply_eval_df = pd.DataFrame(reply_eval_rows)

    # --- Consolidate outputs ---
    consolidated_df = summary_df_full[
        ["support_ticket_id", ticket_col, "generated_summary"]
    ].rename(columns={ticket_col: "raw_ticket_text"})
    consolidated_df = consolidated_df.merge(response_df, on="support_ticket_id", how="left")

    consolidated_csv = paths.out_dir / "consolidated_ticket_outputs.csv"
    consolidated_df.to_csv(consolidated_csv, index=False)

    final_df = consolidated_df.copy()
    if all(c in summary_df_full.columns for c in ["clarity", "coverage", "faithfulness"]):
        final_df = final_df.merge(
            summary_df_full[["support_ticket_id", "clarity", "coverage", "faithfulness"]].rename(
                columns={
                    "clarity": "summary_clarity",
                    "coverage": "summary_coverage",
                    "faithfulness": "summary_faithfulness",
                }
            ),
            on="support_ticket_id",
            how="left",
        )
    if not reply_eval_df.empty:
        final_df = final_df.merge(
            reply_eval_df.rename(
                columns={
                    "relevance": "response_relevance",
                    "empathy_tone": "response_empathy_tone",
                    "accuracy_safety": "response_accuracy_safety",
                    "actionability": "response_actionability",
                    "clarity": "response_clarity",
                    "note": "response_evaluation_note",
                }
            ),
            on="support_ticket_id",
            how="left",
        )

    final_csv = paths.out_dir / "final_consolidated_ticket_outputs.csv"
    final_df.to_csv(final_csv, index=False)

    return {"consolidated_csv": consolidated_csv, "final_csv": final_csv}
