"""Phase-5 run orchestration: parser, payload parsing, dry-run publish, score on empty."""

import json

from advisor import run as RUN
from advisor import config as cfg


def test_parser_has_all_subcommands():
    p = RUN.build_parser()
    for cmd in ("prepare", "publish", "score", "check"):
        args = p.parse_args([cmd] if cmd != "publish" else ["publish"])
        assert args.cmd == cmd


def test_parse_payload_accepts_list_and_dict(tmp_path):
    f1 = tmp_path / "a.json"
    f1.write_text(json.dumps([{"type": "hold", "tier": "hold"}]))
    decisions, closest = RUN._parse_payload(f1)
    assert decisions[0]["type"] == "hold" and closest is None

    f2 = tmp_path / "b.json"
    f2.write_text(json.dumps({"decisions": [{"type": "stream"}], "closest_call": "held X"}))
    decisions, closest = RUN._parse_payload(f2)
    assert closest == "held X" and decisions[0]["type"] == "stream"


def test_publish_dry_run_writes_preview_only(tmp_path, monkeypatch, capsys):
    date = "2026-05-31"
    ctx = {"date": date, "matchup_week": 10, "matchup_day": 3, "matchup_length_days": 7,
           "days_remaining": 4, "opponent": "Rival", "moves_used": 0, "moves_max": 7,
           "winprob": {"overall": {"p_win_matchup": 0.6, "expected_cats_won": 6.5}, "by_cat": {}},
           "data_warnings": []}
    ctx_file = tmp_path / "ctx.json"
    ctx_file.write_text(json.dumps(ctx))
    dec_file = tmp_path / "dec.json"
    dec_file.write_text(json.dumps({"decisions": [{"type": "hold", "tier": "hold"}],
                                    "closest_call": "held Lugo"}))
    preview = tmp_path / "preview.html"

    monkeypatch.setattr(cfg, "context_path", lambda d: ctx_file)
    monkeypatch.setattr(cfg, "scratch_path", lambda name: preview)

    args = RUN.build_parser().parse_args(
        ["publish", "--dry-run", "--date", date, "--decisions", str(dec_file)])
    rc = args.fn(args)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "dry-run"
    assert preview.exists()
    assert "No moves." in preview.read_text()


def test_score_on_empty_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cfg, "DECISIONS_CSV", tmp_path / "nope.csv")
    args = RUN.build_parser().parse_args(["score"])
    args.fn(args)
    out = json.loads(capsys.readouterr().out)
    assert out["n_decisions"] == 0
