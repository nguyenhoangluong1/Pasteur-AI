from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

# Ensure project root is importable when running this file directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import get_settings


NAMESPACE = uuid.UUID("9c6f1225-9d39-4c8a-a9ce-8c0d2ec4d8f1")


@dataclass
class SyntheticPatient:
    code: str
    full_name: str
    summary: str
    conditions: list[str]
    meds: list[dict]
    restrictions: str
    records: list[dict]


def make_patient_id(code: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"patient:{code}"))


def make_config_id(code: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"config:{code}"))


def make_record_id(code: str, idx: int) -> str:
    return str(uuid.uuid5(NAMESPACE, f"record:{code}:{idx}"))


def synthetic_dataset() -> list[SyntheticPatient]:
    return [
        SyntheticPatient(
            code="P001",
            full_name="Nguyen Van An",
            summary="Nam 67 tuoi, tang huyet ap va dai thao duong type 2 trong 8 nam, da tu theo doi huyet ap tai nha.",
            conditions=["tang_huyet_ap", "dai_thao_duong_type_2"],
            meds=[
                {"name": "Amlodipine", "dose": "5mg", "frequency": "sang"},
                {"name": "Metformin", "dose": "500mg", "frequency": "sang-toi"},
            ],
            restrictions="Han che muoi duoi 5g/ngay, khong bo bua sang.",
            records=[
                {"record_type": "encounter", "content": {"chief_complaint": "nhuc dau nhe buoi sang", "home_bp_7d_avg": "148/92", "adherence": "quen thuoc 1-2 lan/tuan"}},
                {"record_type": "lab", "content": {"hba1c_current": 7.4, "hba1c_prev_3m": 7.8, "fasting_glucose": 8.1, "unit": "mmol/L"}},
                {"record_type": "vital", "content": {"clinic_bp": "145/90", "hr": 84, "weight_kg": 70.2, "bmi": 26.1}},
                {"record_type": "care_plan", "content": {"goals_4w": ["huyet ap < 140/90", "duong huyet doi < 7.0"], "actions": ["di bo 30 phut/ngay", "uống thuoc dung gio"], "next_visit": "4 tuan"}},
            ],
        ),
        SyntheticPatient(
            code="P002",
            full_name="Tran Thi Bich",
            summary="Nu 58 tuoi, roi loan lipid mau kem gan nhiem mo do nhe, da thay doi che do an nhung chua deu.",
            conditions=["roi_loan_lipid_mau", "gan_nhiem_mo"],
            meds=[{"name": "Rosuvastatin", "dose": "10mg", "frequency": "toi"}],
            restrictions="Han che do chien, tranh ruou bia.",
            records=[
                {"record_type": "lab", "content": {"ldl_c_current": 4.1, "ldl_c_prev_2m": 4.6, "hdl_c": 1.0, "triglyceride": 2.3, "unit": "mmol/L"}},
                {"record_type": "imaging", "content": {"abd_ultrasound": "gan nhiem mo do 1", "fibrosis_sign": "khong ro"}},
                {"record_type": "diet_recall", "content": {"fried_food_frequency_per_week": 4, "sweet_drinks_per_week": 3, "adherence_level": "thap"}},
                {"record_type": "care_plan", "content": {"goals_8w": ["ldl-c < 2.6"], "actions": ["giam do chien", "ca bien 2 lan/tuan", "di bo 150 phut/tuan"], "next_visit": "8 tuan"}},
            ],
        ),
        SyntheticPatient(
            code="P003",
            full_name="Le Quang Minh",
            summary="Nam 45 tuoi, hen phe quan dai dang, hay kho tho ve dem khi troi lanh hoac gap khoi bui.",
            conditions=["hen_phe_quan"],
            meds=[
                {"name": "Budesonide/Formoterol", "dose": "160/4.5", "frequency": "2 lan/ngay"},
                {"name": "Salbutamol", "dose": "100mcg", "frequency": "khi can"},
            ],
            restrictions="Tranh khoi thuoc la, giu am duong tho.",
            records=[
                {"record_type": "symptom", "content": {"night_cough_per_week": 3, "wheeze": "nhe-den-vua", "rescue_inhaler_use_per_week": 4}},
                {"record_type": "spirometry", "content": {"fev1_percent_pred": 78, "fev1_prev_6m": 72, "pef_variability_percent": 12}},
                {"record_type": "trigger_profile", "content": {"cold_weather": True, "dust_exposure": True, "smoke_exposure": False}},
                {"record_type": "education", "content": {"inhaler_technique_score": "6/10", "note": "can huong dan thao tac hit xit dung cach"}},
            ],
        ),
        SyntheticPatient(
            code="P004",
            full_name="Pham Thu Ha",
            summary="Nu 34 tuoi, suy giap nguyen phat, da dieu tri levothyroxine on dinh hon 1 nam.",
            conditions=["suy_giap"],
            meds=[{"name": "Levothyroxine", "dose": "50mcg", "frequency": "sang luc doi"}],
            restrictions="Uong thuoc truoc an sang 30 phut.",
            records=[
                {"record_type": "lab", "content": {"tsh_current": 3.1, "tsh_prev_3m": 4.8, "ft4": 1.2, "unit": "ng/dL"}},
                {"record_type": "symptom", "content": {"fatigue": "nhe", "cold_intolerance": "thinh thoang", "hair_loss": "giam"}},
                {"record_type": "adherence", "content": {"missed_doses_last_2w": 1, "time_before_breakfast_minutes": 25}},
                {"record_type": "care_plan", "content": {"status": "on dinh", "plan": "giu lieu hien tai", "next_visit": "8 tuan"}},
            ],
        ),
        SyntheticPatient(
            code="P005",
            full_name="Vo Duc Long",
            summary="Nam 72 tuoi, benh than man giai doan 3 do tang huyet ap lau nam, theo doi sat chuc nang than.",
            conditions=["benh_than_man_gd3", "tang_huyet_ap"],
            meds=[
                {"name": "Losartan", "dose": "50mg", "frequency": "sang"},
                {"name": "Furosemide", "dose": "20mg", "frequency": "sang"},
            ],
            restrictions="Han che muoi va nuoc theo huong dan bac si.",
            records=[
                {"record_type": "lab", "content": {"creatinine_current": 1.8, "creatinine_prev_3m": 1.7, "egfr": 42, "potassium": 4.9, "unit": "mg/dL|mL/min/1.73m2|mmol/L"}},
                {"record_type": "vital", "content": {"clinic_bp": "150/88", "home_bp_7d_avg": "146/86", "weight_kg": 64.5, "ankle_edema": "nhe"}},
                {"record_type": "fluid_log", "content": {"daily_intake_ml_avg": 1650, "urine_output_note": "on dinh"}},
                {"record_type": "care_plan", "content": {"salt_limit": "duoi 4g/ngay", "weight_alarm": "tang >1kg/24h", "next_visit": "4 tuan"}},
            ],
        ),
        SyntheticPatient(
            code="P006",
            full_name="Do Thi Lan",
            summary="Nu 29 tuoi, thieu mau thieu sat sau sinh, than phien met moi khi cham con.",
            conditions=["thieu_mau_thieu_sat"],
            meds=[{"name": "Ferrous sulfate", "dose": "325mg", "frequency": "1 vien/ngay sau an"}],
            restrictions="Tang cuong thuc pham giau sat va vitamin C.",
            records=[
                {"record_type": "lab", "content": {"hb_current": 10.2, "hb_prev_6w": 9.4, "ferritin": 11, "mcv": 74, "unit": "g/dL|ng/mL|fL"}},
                {"record_type": "symptom", "content": {"fatigue": "trung binh", "dizziness": "thinh thoang", "palpitation": "khong"}},
                {"record_type": "adherence", "content": {"iron_taken_days_last_week": 5, "side_effect": "tao bon nhe"}},
                {"record_type": "nutrition", "content": {"foods_recommended": ["thit do", "rau xanh dam", "cam"], "tea_after_meal": "nen tranh 1-2h sau uong sat"}},
            ],
        ),
        SyntheticPatient(
            code="P007",
            full_name="Bui Thanh Son",
            summary="Nam 52 tuoi, gout man tinh, con dau tai phat khi an nhieu hai san va uong bia.",
            conditions=["gout_man_tinh"],
            meds=[{"name": "Allopurinol", "dose": "100mg", "frequency": "hang ngay"}],
            restrictions="Tranh noi tang, han che bia ruou, uong du nuoc.",
            records=[
                {"record_type": "lab", "content": {"uric_acid_current": 510, "uric_acid_prev_2m": 590, "unit": "umol/L"}},
                {"record_type": "attack", "content": {"last_attack_days_ago": 14, "joint": "ngon chan cai phai", "pain_score_0_10": 7}},
                {"record_type": "trigger_profile", "content": {"beer_intake_last_week": 3, "seafood_meals_last_week": 2, "water_intake_ml_avg": 1400}},
                {"record_type": "care_plan", "content": {"target_uric_acid": "<360 umol/L", "plan": "duy tri allopurinol, tai kham 6 tuan"}},
            ],
        ),
        SyntheticPatient(
            code="P008",
            full_name="Dang My Linh",
            summary="Nu 40 tuoi, hoi chung ruot kich thich, trieu chung nang hon khi cang thang cong viec.",
            conditions=["ibs"],
            meds=[{"name": "Mebeverine", "dose": "135mg", "frequency": "2 lan/ngay khi can"}],
            restrictions="An thanh nhieu bua nho, han che do cay va caffeine.",
            records=[
                {"record_type": "symptom", "content": {"bloating_days_per_week": 5, "abdominal_pain_score_0_10": 4, "bowel_pattern": "xen ke tao bon va tieu long"}},
                {"record_type": "trigger_profile", "content": {"stress_related": True, "foods_trigger": ["ca phe", "do cay", "sua tuoi"], "sleep_hours_avg": 5.8}},
                {"record_type": "stool_log", "content": {"bristol_scale_majority": 4, "urgent_bowel_movements_per_week": 2}},
                {"record_type": "care_plan", "content": {"actions": ["nhat ky an uong", "tho sau 10 phut/ngay", "giam caffeine"], "followup": "6 tuan"}},
            ],
        ),
        SyntheticPatient(
            code="P009",
            full_name="Hoang Gia Bao",
            summary="Nam 61 tuoi, benh mach vanh sau dat stent, dang on dinh va tu tap di bo hang ngay.",
            conditions=["benh_mach_vanh_sau_stent"],
            meds=[
                {"name": "Aspirin", "dose": "81mg", "frequency": "hang ngay"},
                {"name": "Clopidogrel", "dose": "75mg", "frequency": "hang ngay"},
            ],
            restrictions="Khong tu y ngung thuoc chong ket tap tieu cau.",
            records=[
                {"record_type": "vital", "content": {"clinic_bp": "132/80", "hr": 72, "weight_kg": 67.3}},
                {"record_type": "lab", "content": {"ldl_c_current": 1.8, "ldl_c_prev_3m": 2.2, "unit": "mmol/L"}},
                {"record_type": "symptom", "content": {"chest_pain": "khong", "dyspnea": "khong", "palpitation": "hiem"}},
                {"record_type": "rehab", "content": {"exercise": "di bo 25 phut/ngay", "weekly_sessions": 5, "adherence": "tot"}},
            ],
        ),
        SyntheticPatient(
            code="P010",
            full_name="Nguyen Thi Yen",
            summary="Nu 50 tuoi, tien dai thao duong va beo phi do 1, dang theo chuong trinh thay doi loi song.",
            conditions=["tien_dai_thao_duong", "beo_phi_do_1"],
            meds=[],
            restrictions="Giam duong nuoc ngot, tang van dong 150 phut/tuan.",
            records=[
                {"record_type": "lab", "content": {"hba1c_current": 6.1, "hba1c_prev_3m": 6.4, "fasting_glucose": 6.0, "unit": "mmol/L"}},
                {"record_type": "anthropometry", "content": {"bmi_current": 30.1, "bmi_prev_2m": 31.0, "waist_cm": 92}},
                {"record_type": "lifestyle", "content": {"steps_avg_per_day": 6200, "sweet_drinks_per_week": 2, "late_night_meals_per_week": 3}},
                {"record_type": "care_plan", "content": {"weight_goal_3m": "-4kg", "diet": "giam 20% tinh bot nhanh", "exercise_target": "150 phut/tuan"}},
            ],
        ),
    ]


def main() -> None:
    settings = get_settings()
    database_url = settings.resolved_database_url
    if not database_url.startswith("postgresql"):
        raise RuntimeError("Script nay yeu cau PostgreSQL/Supabase.")

    now = datetime.now(timezone.utc)
    patients = synthetic_dataset()

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            inserted_patients = 0
            inserted_configs = 0
            inserted_records = 0

            for patient in patients:
                patient_id = make_patient_id(patient.code)
                config_id = make_config_id(patient.code)

                cur.execute(
                    """
                    INSERT INTO public.patients (id, full_name, medical_summary, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET full_name = EXCLUDED.full_name,
                        medical_summary = EXCLUDED.medical_summary;
                    """,
                    (patient_id, patient.full_name, patient.summary, now),
                )
                inserted_patients += 1

                cur.execute(
                    """
                    INSERT INTO public.patient_medical_config (
                        id, patient_id, facility_name, medical_summary, chronic_conditions,
                        current_medications, restrictions, language, is_active, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'vi', true, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET facility_name = EXCLUDED.facility_name,
                        medical_summary = EXCLUDED.medical_summary,
                        chronic_conditions = EXCLUDED.chronic_conditions,
                        current_medications = EXCLUDED.current_medications,
                        restrictions = EXCLUDED.restrictions,
                        is_active = true,
                        updated_at = EXCLUDED.updated_at;
                    """,
                    (
                        config_id,
                        patient_id,
                        "Benh vien Da khoa Pasteur Demo",
                        patient.summary,
                        Json(patient.conditions),
                        Json(patient.meds),
                        patient.restrictions,
                        now,
                        now,
                    ),
                )
                inserted_configs += 1

                for idx, record in enumerate(patient.records, start=1):
                    rec_id = make_record_id(patient.code, idx)
                    recorded_at = now - timedelta(days=idx * 14)
                    cur.execute(
                        """
                        INSERT INTO public.medical_records (
                            id, patient_id, record_type, content, recorded_at, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE
                        SET record_type = EXCLUDED.record_type,
                            content = EXCLUDED.content,
                            recorded_at = EXCLUDED.recorded_at;
                        """,
                        (
                            rec_id,
                            patient_id,
                            record["record_type"],
                            Json(record["content"]),
                            recorded_at,
                            now,
                        ),
                    )
                    inserted_records += 1

        conn.commit()

    print(
        json.dumps(
            {
                "patients_upserted": inserted_patients,
                "configs_upserted": inserted_configs,
                "records_upserted": inserted_records,
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
