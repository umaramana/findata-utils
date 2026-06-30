"""Reusable smoke generator for report_pdf — single-date first-assessment sample."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from report_pdf import generate_full_report

D = "2026-06-01"
_ROWS = [
    ("body_measurements", "neck_cm", 15), ("body_measurements", "chest_cm", 35.5),
    ("body_measurements", "waist", 33.5), ("body_measurements", "abdomen_cm", 31.5),
    ("body_measurements", "hips", 38), ("body_measurements", "thigh_cm", 22.5),
    ("body_measurements", "calf_cm", 14.5), ("body_measurements", "shoulder_cm", 11.5),
    ("body_measurements", "forearm_cm", 11),
    ("body_vitals", "weight_kg", 70), ("body_vitals", "height_cm", 166),
    ("body_vitals", "bp_systol", 74), ("body_vitals", "bp_diastol", 134),
    ("body_vitals", "pulse", 51),
    ("physio_1", "pushups", 34), ("physio_1", "squats", 25),
    ("physio_2", "plank", 11), ("physio_2", "cooper_12min", 2),
    ("balance_open", "normal", 20), ("balance_open", "tandem_left", 20),
    ("balance_closed", "normal", 20), ("balance_closed", "tandem_left", 9),
]


def main():
    readings = [{"client_id": "ac5", "component": c, "metric": m, "date": D, "value": v}
                for (c, m, v) in _ROWS]
    result = generate_full_report(
        client_id="ac5", date_from="2026-06-01", date_to="2026-06-30",
        component_ids=["body_measurements", "body_vitals", "physio_1", "physio_2",
                       "balance_open", "balance_closed"],
        grid_density="1x1", all_readings=readings,
        client_profile={"gender": "male", "dob": "1990-06-15"},
        output_dir="smoke_output",
    )
    print(result)


if __name__ == "__main__":
    main()
