from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import get_settings


NAMESPACE = uuid.UUID("9c6f1225-9d39-4c8a-a9ce-8c0d2ec4d8f1")
_WORD_RE = re.compile(r"[a-zA-Z0-9_]+", flags=re.UNICODE)


@dataclass
class SyntheticPatient:
    code: str
    full_name: str
    summary: str
    conditions: list[str]
    meds: list[dict]
    restrictions: str
    records: list[dict]
    dialogue: list[tuple[str, str]]


def make_id(kind: str, *parts: object) -> str:
    key = ":".join([kind] + [str(p) for p in parts])
    return str(uuid.uuid5(NAMESPACE, key))


def _tokenize(text_value: str) -> list[str]:
    return _WORD_RE.findall(text_value.lower())


def _embed_text(text_value: str, dims: int) -> list[float]:
    vec = [0.0] * dims
    tokens = _tokenize(text_value)
    if not tokens:
        return vec
    for tok in tokens:
        digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], byteorder="little", signed=False) % dims
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        return vec
    return [v / norm for v in vec]


def _vec_to_pgvector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def _json_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _build_rag_chunks(patient_id: str, patient: SyntheticPatient, record_ids: list[str]) -> list[tuple[str, str, str]]:
    chunks = [
        (
            f"{patient_id}:patient:base",
            "patient_base",
            f"Họ tên: {patient.full_name}\nTóm tắt: {patient.summary}",
        ),
        (
            f"{patient_id}:config:active",
            "medical_config",
            (
                f"Tóm tắt bổ sung: {patient.summary}\n"
                f"Bệnh nền: {_json_text(patient.conditions)}\n"
                f"Thuốc đang dùng: {_json_text(patient.meds)}\n"
                f"Hạn chế: {patient.restrictions}"
            ),
        ),
    ]
    for idx, (record, rec_id) in enumerate(zip(patient.records, record_ids, strict=False), start=1):
        day = (datetime.now(timezone.utc) - timedelta(days=idx * 14)).strftime("%Y-%m-%d")
        chunk = (
            f"Loại bản ghi: {record['record_type']}\n"
            f"Ngày: {day}\n"
            f"Nội dung: {_json_text(record['content'])}"
        )
        chunks.append((f"{patient_id}:record:{rec_id}", "medical_record", chunk))
    return chunks


def _build_base_dataset() -> list[SyntheticPatient]:
    return [
        SyntheticPatient(
            code="P001",
            full_name="Nguyễn Văn An",
            summary="Nam 67 tuổi, tăng huyết áp và đái tháo đường type 2 trong 8 năm, đã tự theo dõi huyết áp tại nhà.",
            conditions=["tăng_huyết_áp", "đái_tháo_đường_type_2"],
            meds=[{"name": "Amlodipine", "dose": "5mg", "frequency": "sáng"}, {"name": "Metformin", "dose": "500mg", "frequency": "sáng-tối"}],
            restrictions="Hạn chế muối dưới 5g/ngày, không bỏ bữa sáng.",
            records=[
                {"record_type": "encounter", "content": {"chief_complaint": "nhức đầu nhẹ buổi sáng", "home_bp_7d_avg": "148/92", "adherence": "quên thuốc 1-2 lần/tuần"}},
                {"record_type": "lab", "content": {"hba1c_current": 7.4, "hba1c_prev_3m": 7.8, "fasting_glucose": 8.1, "unit": "mmol/L"}},
                {"record_type": "vital", "content": {"clinic_bp": "145/90", "hr": 84, "weight_kg": 70.2, "bmi": 26.1}},
                {"record_type": "care_plan", "content": {"goals_4w": ["huyết áp < 140/90", "đường huyết đói < 7.0"], "actions": ["đi bộ 30 phút/ngày", "uống thuốc đúng giờ"], "next_visit": "4 tuần"}},
            ],
            dialogue=[("Dạo này huyết áp của tôi vẫn cao buổi sáng, tôi nên điều chỉnh gì?", "Anh nên đo huyết áp đúng giờ, giảm muối và giữ thuốc đều mỗi ngày."), ("Tôi hay quên liều chiều metformin.", "Anh có thể đặt nhắc giờ cố định sau bữa tối và ghi nhật ký dùng thuốc.")],
        ),
        SyntheticPatient(
            code="P002",
            full_name="Trần Thị Bích",
            summary="Nữ 58 tuổi, rối loạn lipid máu kèm gan nhiễm mỡ độ nhẹ, đã thay đổi chế độ ăn nhưng chưa đều.",
            conditions=["rối_loạn_lipid_máu", "gan_nhiễm_mỡ"],
            meds=[{"name": "Rosuvastatin", "dose": "10mg", "frequency": "tối"}],
            restrictions="Hạn chế đồ chiên, tránh rượu bia.",
            records=[
                {"record_type": "lab", "content": {"ldl_c_current": 4.1, "ldl_c_prev_2m": 4.6, "hdl_c": 1.0, "triglyceride": 2.3, "unit": "mmol/L"}},
                {"record_type": "imaging", "content": {"abd_ultrasound": "gan nhiễm mỡ độ 1", "fibrosis_sign": "không rõ"}},
                {"record_type": "diet_recall", "content": {"fried_food_frequency_per_week": 4, "sweet_drinks_per_week": 3, "adherence_level": "thấp"}},
                {"record_type": "care_plan", "content": {"goals_8w": ["LDL-C < 2.6"], "actions": ["giảm đồ chiên", "cá biển 2 lần/tuần", "đi bộ 150 phút/tuần"], "next_visit": "8 tuần"}},
            ],
            dialogue=[("Tôi uống statin rồi nhưng mỡ máu vẫn cao.", "Chị cần dùng đều buổi tối và kiểm soát dầu mỡ, đồ ngọt trong 6-8 tuần."), ("Gan nhiễm mỡ có hồi phục được không?", "Có thể cải thiện rõ nếu giảm cân từ từ và hạn chế rượu bia.")],
        ),
        SyntheticPatient(
            code="P003",
            full_name="Lê Quang Minh",
            summary="Nam 45 tuổi, hen phế quản dai dẳng, hay khó thở về đêm khi trời lạnh hoặc gặp khói bụi.",
            conditions=["hen_phế_quản"],
            meds=[{"name": "Budesonide/Formoterol", "dose": "160/4.5", "frequency": "2 lần/ngày"}, {"name": "Salbutamol", "dose": "100mcg", "frequency": "khi cần"}],
            restrictions="Tránh khói thuốc lá, giữ ấm đường thở.",
            records=[
                {"record_type": "symptom", "content": {"night_cough_per_week": 3, "wheeze": "nhẹ-đến-vừa", "rescue_inhaler_use_per_week": 4}},
                {"record_type": "spirometry", "content": {"fev1_percent_pred": 78, "fev1_prev_6m": 72, "pef_variability_percent": 12}},
                {"record_type": "trigger_profile", "content": {"cold_weather": True, "dust_exposure": True, "smoke_exposure": False}},
                {"record_type": "education", "content": {"inhaler_technique_score": "6/10", "note": "cần hướng dẫn thao tác hít xịt đúng cách"}},
            ],
            dialogue=[("Tôi vẫn lên cơn khò khè về đêm dù có dùng thuốc xịt.", "Anh cần kiểm tra lại kỹ thuật xịt và tránh tối đa yếu tố khởi phát như bụi, lạnh."), ("Có nên dùng thuốc cắt cơn mỗi ngày không?", "Không nên lạm dụng, chỉ dùng khi cần và ưu tiên thuốc kiểm soát đều.")],
        ),
        SyntheticPatient(
            code="P004",
            full_name="Phạm Thu Hà",
            summary="Nữ 34 tuổi, suy giáp nguyên phát, đã điều trị levothyroxine ổn định hơn 1 năm.",
            conditions=["suy_giáp"],
            meds=[{"name": "Levothyroxine", "dose": "50mcg", "frequency": "sáng lúc đói"}],
            restrictions="Uống thuốc trước ăn sáng 30 phút.",
            records=[
                {"record_type": "lab", "content": {"tsh_current": 3.1, "tsh_prev_3m": 4.8, "ft4": 1.2, "unit": "ng/dL"}},
                {"record_type": "symptom", "content": {"fatigue": "nhẹ", "cold_intolerance": "thỉnh thoảng", "hair_loss": "giảm"}},
                {"record_type": "adherence", "content": {"missed_doses_last_2w": 1, "time_before_breakfast_minutes": 25}},
                {"record_type": "care_plan", "content": {"status": "ổn định", "plan": "giữ liều hiện tại", "next_visit": "8 tuần"}},
            ],
            dialogue=[("Tôi hay quên uống thuốc trước ăn sáng.", "Chị nên đặt báo thức sớm 30 phút và để thuốc cạnh ly nước."), ("TSH của tôi vậy đã ổn chưa?", "Mức hiện tại khá ổn, nên duy trì liều và theo dõi định kỳ.")],
        ),
        SyntheticPatient(
            code="P005",
            full_name="Võ Đức Long",
            summary="Nam 72 tuổi, bệnh thận mạn giai đoạn 3 do tăng huyết áp lâu năm, theo dõi sát chức năng thận.",
            conditions=["bệnh_thận_mạn_gđ3", "tăng_huyết_áp"],
            meds=[{"name": "Losartan", "dose": "50mg", "frequency": "sáng"}, {"name": "Furosemide", "dose": "20mg", "frequency": "sáng"}],
            restrictions="Hạn chế muối và nước theo hướng dẫn bác sĩ.",
            records=[
                {"record_type": "lab", "content": {"creatinine_current": 1.8, "creatinine_prev_3m": 1.7, "egfr": 42, "potassium": 4.9, "unit": "mg/dL|mL/min/1.73m2|mmol/L"}},
                {"record_type": "vital", "content": {"clinic_bp": "150/88", "home_bp_7d_avg": "146/86", "weight_kg": 64.5, "ankle_edema": "nhẹ"}},
                {"record_type": "fluid_log", "content": {"daily_intake_ml_avg": 1650, "urine_output_note": "ổn định"}},
                {"record_type": "care_plan", "content": {"salt_limit": "dưới 4g/ngày", "weight_alarm": "tăng >1kg/24h", "next_visit": "4 tuần"}},
            ],
            dialogue=[("Tôi có cần giảm thêm lượng nước uống không?", "Anh nên theo đúng mức bác sĩ thận chỉ định, tránh tự giảm quá mức."), ("Phù chân chiều tối có đáng lo không?", "Cần theo dõi cân nặng và phù, nếu tăng nhanh nên tái khám sớm.")],
        ),
        SyntheticPatient(
            code="P006",
            full_name="Đỗ Thị Lan",
            summary="Nữ 29 tuổi, thiếu máu thiếu sắt sau sinh, than phiền mệt mỏi khi chăm con.",
            conditions=["thiếu_máu_thiếu_sắt"],
            meds=[{"name": "Ferrous sulfate", "dose": "325mg", "frequency": "1 viên/ngày sau ăn"}],
            restrictions="Tăng cường thực phẩm giàu sắt và vitamin C.",
            records=[
                {"record_type": "lab", "content": {"hb_current": 10.2, "hb_prev_6w": 9.4, "ferritin": 11, "mcv": 74, "unit": "g/dL|ng/mL|fL"}},
                {"record_type": "symptom", "content": {"fatigue": "trung bình", "dizziness": "thỉnh thoảng", "palpitation": "không"}},
                {"record_type": "adherence", "content": {"iron_taken_days_last_week": 5, "side_effect": "táo bón nhẹ"}},
                {"record_type": "nutrition", "content": {"foods_recommended": ["thịt đỏ", "rau xanh đậm", "cam"], "tea_after_meal": "nên tránh 1-2h sau uống sắt"}},
            ],
            dialogue=[("Tôi uống sắt nhưng vẫn mệt mỏi.", "Chị cần dùng đều hơn và kết hợp thực phẩm giàu sắt cùng vitamin C."), ("Uống sắt bị táo bón thì xử lý sao?", "Tăng nước, chất xơ và báo bác sĩ để cân nhắc đổi dạng sắt.")],
        ),
        SyntheticPatient(
            code="P007",
            full_name="Bùi Thanh Sơn",
            summary="Nam 52 tuổi, gout mạn tính, cơn đau tái phát khi ăn nhiều hải sản và uống bia.",
            conditions=["gout_mạn_tính"],
            meds=[{"name": "Allopurinol", "dose": "100mg", "frequency": "hằng ngày"}],
            restrictions="Tránh nội tạng, hạn chế bia rượu, uống đủ nước.",
            records=[
                {"record_type": "lab", "content": {"uric_acid_current": 510, "uric_acid_prev_2m": 590, "unit": "umol/L"}},
                {"record_type": "attack", "content": {"last_attack_days_ago": 14, "joint": "ngón chân cái phải", "pain_score_0_10": 7}},
                {"record_type": "trigger_profile", "content": {"beer_intake_last_week": 3, "seafood_meals_last_week": 2, "water_intake_ml_avg": 1400}},
                {"record_type": "care_plan", "content": {"target_uric_acid": "<360 umol/L", "plan": "duy trì allopurinol, tái khám 6 tuần"}},
            ],
            dialogue=[("Tôi hết đau rồi có cần uống allopurinol nữa không?", "Vẫn cần duy trì đều để phòng cơn gout tái phát."), ("Tôi nên kiêng những món gì?", "Hạn chế bia rượu, nội tạng và hải sản giàu purin.")],
        ),
        SyntheticPatient(
            code="P008",
            full_name="Đặng Mỹ Linh",
            summary="Nữ 40 tuổi, hội chứng ruột kích thích, triệu chứng nặng hơn khi căng thẳng công việc.",
            conditions=["ibs"],
            meds=[{"name": "Mebeverine", "dose": "135mg", "frequency": "2 lần/ngày khi cần"}],
            restrictions="Ăn thành nhiều bữa nhỏ, hạn chế đồ cay và caffeine.",
            records=[
                {"record_type": "symptom", "content": {"bloating_days_per_week": 5, "abdominal_pain_score_0_10": 4, "bowel_pattern": "xen kẽ táo bón và tiêu lỏng"}},
                {"record_type": "trigger_profile", "content": {"stress_related": True, "foods_trigger": ["cà phê", "đồ cay", "sữa tươi"], "sleep_hours_avg": 5.8}},
                {"record_type": "stool_log", "content": {"bristol_scale_majority": 4, "urgent_bowel_movements_per_week": 2}},
                {"record_type": "care_plan", "content": {"actions": ["nhật ký ăn uống", "thở sâu 10 phút/ngày", "giảm caffeine"], "followup": "6 tuần"}},
            ],
            dialogue=[("Tôi đau bụng nhiều khi căng thẳng công việc.", "Bạn nên kết hợp quản lý stress và điều chỉnh chế độ ăn theo nhật ký."), ("Tôi có cần nội soi lại không?", "Nếu có dấu hiệu cảnh báo như sụt cân, đi ngoài máu thì nên khám sớm.")],
        ),
        SyntheticPatient(
            code="P009",
            full_name="Hoàng Gia Bảo",
            summary="Nam 61 tuổi, bệnh mạch vành sau đặt stent, đang ổn định và tự tập đi bộ hằng ngày.",
            conditions=["bệnh_mạch_vành_sau_stent"],
            meds=[{"name": "Aspirin", "dose": "81mg", "frequency": "hằng ngày"}, {"name": "Clopidogrel", "dose": "75mg", "frequency": "hằng ngày"}],
            restrictions="Không tự ý ngưng thuốc chống kết tập tiểu cầu.",
            records=[
                {"record_type": "vital", "content": {"clinic_bp": "132/80", "hr": 72, "weight_kg": 67.3}},
                {"record_type": "lab", "content": {"ldl_c_current": 1.8, "ldl_c_prev_3m": 2.2, "unit": "mmol/L"}},
                {"record_type": "symptom", "content": {"chest_pain": "không", "dyspnea": "không", "palpitation": "hiếm"}},
                {"record_type": "rehab", "content": {"exercise": "đi bộ 25 phút/ngày", "weekly_sessions": 5, "adherence": "tốt"}},
            ],
            dialogue=[("Sau đặt stent bao lâu thì giảm thuốc được?", "Anh cần theo đúng phác đồ bác sĩ tim mạch, không tự giảm thuốc."), ("Tập đi bộ mỗi ngày có đủ chưa?", "Rất tốt, anh có thể tăng dần nhưng tránh gắng sức quá mức.")],
        ),
        SyntheticPatient(
            code="P010",
            full_name="Nguyễn Thị Yến",
            summary="Nữ 50 tuổi, tiền đái tháo đường và béo phì độ 1, đang theo chương trình thay đổi lối sống.",
            conditions=["tiền_đái_tháo_đường", "béo_phì_độ_1"],
            meds=[],
            restrictions="Giảm đường nước ngọt, tăng vận động 150 phút/tuần.",
            records=[
                {"record_type": "lab", "content": {"hba1c_current": 6.1, "hba1c_prev_3m": 6.4, "fasting_glucose": 6.0, "unit": "mmol/L"}},
                {"record_type": "anthropometry", "content": {"bmi_current": 30.1, "bmi_prev_2m": 31.0, "waist_cm": 92}},
                {"record_type": "lifestyle", "content": {"steps_avg_per_day": 6200, "sweet_drinks_per_week": 2, "late_night_meals_per_week": 3}},
                {"record_type": "care_plan", "content": {"weight_goal_3m": "-4kg", "diet": "giảm 20% tinh bột nhanh", "exercise_target": "150 phút/tuần"}},
            ],
            dialogue=[("Tôi giảm cân chậm, có cách nào hiệu quả hơn?", "Bạn nên giữ thâm hụt calo vừa phải và tăng vận động đều mỗi tuần."), ("Tiền đái tháo đường có thể hồi phục không?", "Có thể cải thiện tốt nếu kiểm soát cân nặng và ăn uống bền vững.")],
        ),
    ]


def _extra_dataset() -> list[SyntheticPatient]:
    cases: list[SyntheticPatient] = []
    specs = [
        ("P011", "Lý Minh Khôi", "Nam 63 tuổi, COPD mức trung bình, ho khạc đờm nhiều buổi sáng, khó thở khi gắng sức.", ["copd"], [{"name": "Tiotropium", "dose": "18mcg", "frequency": "1 lần/ngày"}, {"name": "Salbutamol", "dose": "100mcg", "frequency": "khi cần"}], "Tránh khói bụi, tiêm cúm hằng năm, tập thở môi chúm."),
        ("P012", "Phan Hồng Nhung", "Nữ 49 tuổi, đau nửa đầu mạn, cơn đau tăng khi thiếu ngủ và stress.", ["migraine_mạn"], [{"name": "Topiramate", "dose": "25mg", "frequency": "tối"}, {"name": "Sumatriptan", "dose": "50mg", "frequency": "khi cơn"}], "Giữ giờ ngủ đều, hạn chế cà phê sau 16h."),
        ("P013", "Đặng Quốc Vinh", "Nam 71 tuổi, rung nhĩ không do van tim, đang dùng thuốc chống đông.", ["rung_nhĩ", "tăng_huyết_áp"], [{"name": "Apixaban", "dose": "5mg", "frequency": "2 lần/ngày"}, {"name": "Bisoprolol", "dose": "2.5mg", "frequency": "sáng"}], "Không tự ngưng thuốc chống đông, tránh va chạm mạnh."),
        ("P014", "Ngô Mỹ Duyên", "Nữ 56 tuổi, viêm khớp dạng thấp, cứng khớp buổi sáng khoảng 45 phút.", ["viêm_khớp_dạng_thấp"], [{"name": "Methotrexate", "dose": "10mg", "frequency": "1 lần/tuần"}, {"name": "Folic acid", "dose": "5mg", "frequency": "hôm sau methotrexate"}], "Theo dõi men gan định kỳ, tập vận động khớp nhẹ."),
        ("P015", "Tạ Thanh Bình", "Nam 44 tuổi, trào ngược dạ dày thực quản, nóng rát sau ăn tối.", ["gerd"], [{"name": "Esomeprazole", "dose": "40mg", "frequency": "sáng trước ăn"}, {"name": "Gaviscon", "dose": "10ml", "frequency": "sau ăn"}], "Không nằm ngay sau ăn, kê cao đầu giường."),
        ("P016", "Vũ Diễm Quỳnh", "Nữ 37 tuổi, hội chứng buồng trứng đa nang, rối loạn kinh nguyệt và tăng cân.", ["pcos", "tiền_đái_tháo_đường"], [{"name": "Metformin XR", "dose": "500mg", "frequency": "tối"}, {"name": "Inositol", "dose": "2g", "frequency": "2 lần/ngày"}], "Giảm tinh bột nhanh, tăng vận động đều."),
        ("P017", "Lê Hoài Nam", "Nam 68 tuổi, suy tim EF giảm nhẹ, phù chân cuối ngày.", ["suy_tim", "bệnh_mạch_vành"], [{"name": "Sacubitril/Valsartan", "dose": "49/51mg", "frequency": "2 lần/ngày"}, {"name": "Spironolactone", "dose": "25mg", "frequency": "sáng"}], "Hạn chế muối <2g/ngày, theo dõi cân nặng mỗi sáng."),
        ("P018", "Hoàng Anh Thư", "Nữ 33 tuổi, viêm da cơ địa, ngứa tăng khi thời tiết hanh khô.", ["viêm_da_cơ_địa"], [{"name": "Cetirizine", "dose": "10mg", "frequency": "tối"}, {"name": "Hydrocortisone cream", "dose": "bôi mỏng", "frequency": "khi bùng phát"}], "Dưỡng ẩm 2-3 lần/ngày, tránh xà phòng mạnh."),
        ("P019", "Nguyễn Đức Tùng", "Nam 59 tuổi, tăng sinh lành tính tuyến tiền liệt, tiểu đêm 3 lần.", ["bph"], [{"name": "Tamsulosin", "dose": "0.4mg", "frequency": "tối"}, {"name": "Finasteride", "dose": "5mg", "frequency": "sáng"}], "Giảm uống nước sau 20h, hạn chế cà phê buổi tối."),
        ("P020", "Trần Ngọc Mai", "Nữ 62 tuổi, loãng xương sau mãn kinh, từng đau lưng do lún nhẹ đốt sống.", ["loãng_xương"], [{"name": "Alendronate", "dose": "70mg", "frequency": "1 lần/tuần"}, {"name": "Calcium+D3", "dose": "1 viên", "frequency": "sau ăn trưa"}], "Đi bộ chịu lực hằng ngày, phòng ngừa té ngã."),
        ("P021", "Phạm Gia Hân", "Nữ 28 tuổi, rối loạn lo âu lan tỏa, mất ngủ đầu giấc.", ["rối_loạn_lo_âu"], [{"name": "Sertraline", "dose": "50mg", "frequency": "sáng"}, {"name": "Melatonin", "dose": "3mg", "frequency": "trước ngủ"}], "Giữ vệ sinh giấc ngủ, giảm thời gian màn hình buổi tối."),
        ("P022", "Bùi Xuân Trường", "Nam 54 tuổi, viêm gan B mạn, men gan dao động nhẹ.", ["viêm_gan_b_mạn"], [{"name": "Tenofovir", "dose": "300mg", "frequency": "sáng"}], "Không rượu bia, kiểm tra men gan và HBV DNA định kỳ."),
        ("P023", "Đỗ Thanh Vy", "Nữ 46 tuổi, cường giáp Graves đã ổn định một phần với thuốc kháng giáp.", ["cường_giáp_graves"], [{"name": "Thiamazole", "dose": "10mg", "frequency": "sáng"}, {"name": "Propranolol", "dose": "10mg", "frequency": "khi hồi hộp"}], "Không tự chỉnh liều, tái khám nội tiết đúng hẹn."),
        ("P024", "Mai Hữu Phúc", "Nam 39 tuổi, viêm loét đại tràng mức nhẹ, đi ngoài phân lỏng xen máu ít khi stress.", ["viêm_loét_đại_tràng"], [{"name": "Mesalamine", "dose": "2g", "frequency": "chia 2 lần/ngày"}], "Theo dõi số lần đi cầu và dấu hiệu mất nước."),
        ("P025", "Lâm Bảo Châu", "Nữ 65 tuổi, thoái hóa khớp gối hai bên, đau tăng khi leo cầu thang.", ["thoái_hóa_khớp_gối"], [{"name": "Paracetamol", "dose": "500mg", "frequency": "khi đau"}, {"name": "Glucosamine", "dose": "1500mg", "frequency": "1 lần/ngày"}], "Giảm cân nhẹ, tập cơ tứ đầu đùi."),
        ("P026", "Tô Minh Đức", "Nam 47 tuổi, ngưng thở khi ngủ mức vừa, buồn ngủ ban ngày.", ["osa"], [{"name": "CPAP", "dose": "áp lực 8cmH2O", "frequency": "mỗi đêm"}], "Duy trì cân nặng, tránh rượu trước ngủ."),
        ("P027", "Nguyễn Hải Yến", "Nữ 52 tuổi, tăng huyết áp kháng trị, đã dùng 3 nhóm thuốc.", ["tăng_huyết_áp_kháng_trị"], [{"name": "Amlodipine", "dose": "10mg", "frequency": "sáng"}, {"name": "Valsartan", "dose": "160mg", "frequency": "sáng"}, {"name": "Hydrochlorothiazide", "dose": "25mg", "frequency": "sáng"}], "Đo huyết áp tại nhà 2 lần/ngày, hạn chế muối nghiêm ngặt."),
        ("P028", "Phan Tuấn Kiệt", "Nam 35 tuổi, viêm mũi dị ứng quanh năm, nghẹt mũi về đêm.", ["viêm_mũi_dị_ứng"], [{"name": "Fluticasone nasal", "dose": "2 nhát", "frequency": "mỗi tối"}, {"name": "Loratadine", "dose": "10mg", "frequency": "khi cần"}], "Rửa mũi nước muối, giảm tiếp xúc bụi nhà."),
        ("P029", "Đinh Thu Hà", "Nữ 60 tuổi, đái tháo đường type 2 kèm bệnh thần kinh ngoại biên nhẹ.", ["đái_tháo_đường_type_2", "biến_chứng_thần_kinh"], [{"name": "Metformin", "dose": "1000mg", "frequency": "sáng-tối"}, {"name": "Gabapentin", "dose": "300mg", "frequency": "tối"}], "Kiểm tra bàn chân hằng ngày, đi giày mềm vừa chân."),
        ("P030", "Võ Khánh Linh", "Nữ 42 tuổi, lạc nội mạc tử cung, đau bụng kinh nặng theo chu kỳ.", ["lạc_nội_mạc_tử_cung"], [{"name": "Dienogest", "dose": "2mg", "frequency": "1 lần/ngày"}, {"name": "Ibuprofen", "dose": "400mg", "frequency": "khi đau"}], "Theo dõi mức độ đau theo chu kỳ, tái khám phụ khoa định kỳ."),
    ]
    for idx, (code, name, summary, conditions, meds, restrictions) in enumerate(specs, start=1):
        cases.append(
            SyntheticPatient(
                code=code,
                full_name=name,
                summary=summary,
                conditions=conditions,
                meds=meds,
                restrictions=restrictions,
                records=[
                    {"record_type": "symptom", "content": {"main_issue": summary.split(",")[1].strip(), "severity_scale_0_10": 4 + (idx % 4), "sleep_impact": "có" if idx % 2 else "nhẹ"}},
                    {"record_type": "lab", "content": {"marker_a": round(1.2 + (idx * 0.17), 2), "marker_b": round(2.1 + (idx * 0.21), 2), "trend": "cải thiện nhẹ" if idx % 2 else "dao động", "unit": "chuẩn nội bộ"}},
                    {"record_type": "adherence", "content": {"missed_doses_last_2w": idx % 3, "barrier": "quên giờ" if idx % 2 else "bận công việc", "self_note": "đang cố gắng duy trì đều"}},
                    {"record_type": "care_plan", "content": {"next_visit": f"{4 + (idx % 5)} tuần", "goals": ["ổn định triệu chứng", "giảm đợt bùng phát"], "home_actions": ["uống thuốc đúng giờ", "theo dõi triệu chứng mỗi ngày"]}},
                ],
                dialogue=[
                    ("Tình trạng hiện tại của tôi cần lưu ý gì trước?", "Bạn nên ưu tiên tuân thủ thuốc và theo dõi dấu hiệu cảnh báo sớm mỗi ngày."),
                    ("Tôi có cần đổi lối sống thêm không?", "Có, bạn nên điều chỉnh ăn ngủ và vận động đều theo kế hoạch đã ghi."),
                ],
            )
        )
    return cases


def synthetic_dataset() -> list[SyntheticPatient]:
    return _build_base_dataset() + _extra_dataset()


def main() -> None:
    settings = get_settings()
    database_url = settings.resolved_database_url
    if not database_url.startswith("postgresql"):
        raise RuntimeError("Script nay yeu cau PostgreSQL/Supabase.")

    now = datetime.now(timezone.utc)
    patients = synthetic_dataset()
    dims = max(32, int(settings.rag_embedding_dims))

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            stats = {
                "patients_upserted": 0,
                "configs_upserted": 0,
                "records_upserted": 0,
                "conversations_upserted": 0,
                "messages_upserted": 0,
                "rag_chunks_upserted": 0,
            }
            for patient in patients:
                patient_id = make_id("patient", patient.code)
                config_id = make_id("config", patient.code)
                cur.execute(
                    """
                    INSERT INTO public.patients (id, full_name, medical_summary, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET full_name = EXCLUDED.full_name, medical_summary = EXCLUDED.medical_summary;
                    """,
                    (patient_id, patient.full_name, patient.summary, now),
                )
                stats["patients_upserted"] += 1
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
                    (config_id, patient_id, "Bệnh viện Đa khoa Pasteur Demo", patient.summary, Json(patient.conditions), Json(patient.meds), patient.restrictions, now, now),
                )
                stats["configs_upserted"] += 1
                record_ids: list[str] = []
                for idx, record in enumerate(patient.records, start=1):
                    rec_id = make_id("record", patient.code, idx)
                    record_ids.append(rec_id)
                    recorded_at = now - timedelta(days=idx * 14)
                    cur.execute(
                        """
                        INSERT INTO public.medical_records (id, patient_id, record_type, content, recorded_at, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE
                        SET record_type = EXCLUDED.record_type, content = EXCLUDED.content, recorded_at = EXCLUDED.recorded_at;
                        """,
                        (rec_id, patient_id, record["record_type"], Json(record["content"]), recorded_at, now),
                    )
                    stats["records_upserted"] += 1
                conv_id = make_id("conversation", patient.code, 1)
                cur.execute(
                    """
                    INSERT INTO public.conversations (id, patient_id, title, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET title = EXCLUDED.title;
                    """,
                    (conv_id, patient_id, f"Theo dõi bệnh án {patient.full_name}", now - timedelta(days=2)),
                )
                stats["conversations_upserted"] += 1
                msg_idx = 0
                for user_text, ai_text in patient.dialogue:
                    msg_idx += 1
                    cur.execute(
                        """
                        INSERT INTO public.messages (id, conversation_id, role, content, created_at)
                        VALUES (%s, %s, 'USER', %s, %s)
                        ON CONFLICT (id) DO UPDATE
                        SET content = EXCLUDED.content;
                        """,
                        (make_id("message", patient.code, msg_idx), conv_id, user_text, now - timedelta(days=1, minutes=10 - msg_idx)),
                    )
                    stats["messages_upserted"] += 1
                    msg_idx += 1
                    cur.execute(
                        """
                        INSERT INTO public.messages (id, conversation_id, role, content, created_at)
                        VALUES (%s, %s, 'ASSISTANT', %s, %s)
                        ON CONFLICT (id) DO UPDATE
                        SET content = EXCLUDED.content;
                        """,
                        (make_id("message", patient.code, msg_idx), conv_id, ai_text, now - timedelta(days=1, minutes=10 - msg_idx)),
                    )
                    stats["messages_upserted"] += 1
                for chunk_id, source_type, content in _build_rag_chunks(patient_id, patient, record_ids):
                    cur.execute(
                        """
                        INSERT INTO public.rag_chunks (chunk_id, patient_id, source_type, content, embedding, updated_at)
                        VALUES (%s, CAST(%s AS uuid), %s, %s, CAST(%s AS vector), %s)
                        ON CONFLICT (chunk_id) DO UPDATE
                        SET source_type = EXCLUDED.source_type,
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            updated_at = EXCLUDED.updated_at;
                        """,
                        (chunk_id, patient_id, source_type, content, _vec_to_pgvector_literal(_embed_text(content, dims)), now),
                    )
                    stats["rag_chunks_upserted"] += 1
        conn.commit()

    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
