"""Ce que le trafic deja passe dit d'une source, et ce qu'il ne dit pas.

Aucun de ces tests n'ouvre de connexion, et l'un d'eux le verifie plutot que
de l'affirmer : c'est le trait principal du module.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from x10_client import Availability, observe


def _write_journal(state: Path, lines: list[dict[str, Any]]) -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / "runs.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8"
    )


def _journal_line(
    source: str, outcome: str, duration_ns: int, size_bytes: int, offset_h: int = 0
) -> dict[str, Any]:
    timestamp = datetime.now(UTC) - timedelta(hours=offset_h)
    return {
        "source": source,
        "finished_at": timestamp.isoformat(),
        "acquisition": {
            "outcome": outcome,
            "duration_ns": duration_ns,
            "bytes_downloaded": size_bytes,
        },
    }


def test_sans_historique_on_ne_constate_rien(tmp_path):
    assert observe(tmp_path) == ()


def test_le_taux_est_none_et_non_zero_quand_rien_n_est_observe():
    """Zéro ferait passer une absence de mesure pour un échec complet — le
    genre de silence que X10 traque ailleurs."""
    empty = Availability(
        source="s",
        runs=0,
        successes=0,
        usable=0,
        last_run=None,
        median_duration_ms=None,
        bytes_total=0,
    )
    assert empty.success_rate is None
    assert empty.usable_rate is None


def test_le_constat_se_deduit_du_trafic_deja_passe(tmp_path):
    _write_journal(
        tmp_path,
        [
            _journal_line("arome", "success", 2_000_000, 1000, offset_h=2),
            _journal_line("arome", "failure", 4_000_000, 0, offset_h=1),
            _journal_line("arome", "success", 6_000_000, 2000, offset_h=0),
        ],
    )
    (availability,) = observe(tmp_path)
    assert availability.source == "arome"
    assert availability.runs == 3
    assert availability.successes == 2
    assert availability.success_rate == pytest.approx(2 / 3)
    assert availability.median_duration_ms == pytest.approx(4.0)
    assert availability.bytes_total == 3000


def test_les_sources_sont_distinguees(tmp_path):
    _write_journal(
        tmp_path, [_journal_line("arome", "success", 1, 1), _journal_line("ifs", "failure", 1, 0)]
    )
    assert [c.source for c in observe(tmp_path)] == ["arome", "ifs"]
    assert [c.source for c in observe(tmp_path, "ifs")] == ["ifs"]


def test_une_ligne_tronquee_ne_perd_pas_l_historique(tmp_path):
    """Une écriture interrompue laisse une ligne incomplète. La rejeter avec
    tout le fichier coûterait plus que de la passer."""
    truncated = '{"source": "aro'
    (tmp_path / "runs.jsonl").write_text(
        json.dumps(_journal_line("arome", "success", 1, 10)) + "\n" + truncated + "\n",
        encoding="utf-8",
    )
    (availability,) = observe(tmp_path)
    assert availability.runs == 1


def test_constater_n_emet_aucune_requete(tmp_path, monkeypatch):
    """Le trait principal du module, vérifié plutôt qu'affirmé."""
    import socket

    def forbidden(*_args, **_kwargs):
        raise AssertionError("observe() a tenté d'ouvrir une connexion")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    _write_journal(tmp_path, [_journal_line("arome", "success", 1, 10)])
    assert observe(tmp_path)[0].runs == 1


def test_une_ligne_vide_est_passee_sans_bruit(tmp_path):
    """Un journal en ajout finit souvent par un saut de ligne, et un fichier
    recopié en gagne parfois un second."""
    (tmp_path / "runs.jsonl").write_text(
        json.dumps(_journal_line("arome", "success", 1, 10)) + "\n\n   \n", encoding="utf-8"
    )
    (availability,) = observe(tmp_path)
    assert availability.runs == 1
