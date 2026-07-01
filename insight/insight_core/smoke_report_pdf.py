"""Reusable smoke generator for report_pdf — 2-date, real-value fixture
reconstructed from vip_001_2026-06-30_full_report_v8.pdf (values copied
directly off that PDF), remapped onto the current metric_master keys:
Shoulder -> arms, Situps -> crunches, Single Left/Right -> Left Up/Right Up."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from report_pdf import generate_full_report

JAN, JUN = "2026-01-01", "2026-06-01"

_ROWS = [
    # body_measurements (inches) — Jan 2026, Jun 2026
    ("body_measurements", "neck",     JAN, 38),   ("body_measurements", "neck",     JUN, 37.8),
    ("body_measurements", "chest",    JAN, 95),   ("body_measurements", "chest",    JUN, 93.5),
    ("body_measurements", "waist",    JAN, 88),   ("body_measurements", "waist",    JUN, 85),
    ("body_measurements", "abdomen",  JAN, 91),   ("body_measurements", "abdomen",  JUN, 88),
    ("body_measurements", "hips",     JAN, 96),   ("body_measurements", "hips",     JUN, 94.5),
    ("body_measurements", "thighs",   JAN, 58),   ("body_measurements", "thighs",   JUN, 57),
    ("body_measurements", "calves",   JAN, 37),   ("body_measurements", "calves",   JUN, 36.5),
    ("body_measurements", "arms",     JAN, 42),   ("body_measurements", "arms",     JUN, 42),
    ("body_measurements", "forearms", JAN, 29),   ("body_measurements", "forearms", JUN, 28.5),

    # body_vitals — Jan 2026, Jun 2026
    ("body_vitals", "weight_kg",  JAN, 82),   ("body_vitals", "weight_kg",  JUN, 80.5),
    ("body_vitals", "height_cm",  JAN, 175),  ("body_vitals", "height_cm",  JUN, 175),
    ("body_vitals", "bp_systol",  JAN, 128),  ("body_vitals", "bp_systol",  JUN, 122),
    ("body_vitals", "bp_diastol", JAN, 84),   ("body_vitals", "bp_diastol", JUN, 80),
    ("body_vitals", "pulse",      JUN, 68),   # gauge shows latest reading only
    ("body_vitals", "fat_pct",    JAN, 26.9), ("body_vitals", "fat_pct",    JUN, 24.5),
    ("body_vitals", "muscle_pct", JAN, 29.4), ("body_vitals", "muscle_pct", JUN, 31.2),

    # physio_1 — Jan 2026, Jun 2026
    ("physio_1", "pushups",  JAN, 20), ("physio_1", "pushups",  JUN, 25),
    ("physio_1", "squats",   JAN, 30), ("physio_1", "squats",   JUN, 35),
    ("physio_1", "crunches", JAN, 22), ("physio_1", "crunches", JUN, 28),

    # balance_open — Jun 2026 only (matches v8, no Eyes-Open data for Jan)
    ("balance_open", "balance_normal_open",      JUN, 22),
    ("balance_open", "balance_tandem_left_open",  JUN, 18),
    ("balance_open", "balance_tandem_right_open", JUN, 20),
    ("balance_open", "balance_left_up_open",      JUN, 14),
    ("balance_open", "balance_right_up_open",     JUN, 16),

    # physio_2 — new bucket-3 section (testing "does adding more heatmaps
    # break anything" — should just make the page taller, no other change)
    ("physio_2", "plank",             JUN, 45),
    ("physio_2", "right_side_plank",  JUN, 30),
    ("physio_2", "left_side_plank",   JUN, 28),
    ("physio_2", "hold_40deg",        JUN, 20),
    ("physio_2", "sorenson_hold",     JUN, 60),

    # physio_3 — new bucket-3 section
    ("physio_3", "cooper_test",  JUN, 1.8),
    ("physio_3", "flexibility",  JUN, 12),

    # balance_closed — new bucket-3 section
    ("balance_closed", "balance_normal_closed",      JUN, 20),
    ("balance_closed", "balance_tandem_left_closed",  JUN, 11),
    ("balance_closed", "balance_tandem_right_closed", JUN, 9),
    ("balance_closed", "balance_left_up_closed",      JUN, 6),
    ("balance_closed", "balance_right_up_closed",     JUN, 7),
]


def main():
    readings = [{"client_id": "vip_001", "component": c, "metric": m, "date": d, "value": v}
                for (c, m, d, v) in _ROWS]
    result = generate_full_report(
        client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
        component_ids=["body_measurements", "body_vitals", "physio_1", "physio_2",
                       "physio_3", "balance_open", "balance_closed"],
        grid_density="3x2", all_readings=readings,
        client_profile={"gender": "female", "dob": "1990-06-15"},
        output_dir="smoke_output",
    )
    print(result)


if __name__ == "__main__":
    main()
