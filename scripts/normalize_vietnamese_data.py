from __future__ import annotations

import json

from sqlalchemy import text

from core.db.session import engine


PATIENT_NAME_MAP = {
    "Nguyen Thi Yen": "Nguyễn Thị Yến",
    "Hoang Gia Bao": "Hoàng Gia Bảo",
    "Dang My Linh": "Đặng Mỹ Linh",
    "Bui Thanh Son": "Bùi Thanh Sơn",
    "Do Thi Lan": "Đỗ Thị Lan",
    "Vo Duc Long": "Võ Đức Long",
    "Pham Thu Ha": "Phạm Thu Hà",
    "Le Quang Minh": "Lê Quang Minh",
    "Tran Thi Bich": "Trần Thị Bích",
    "Nguyen Van An": "Nguyễn Văn An",
}

MEDICAL_SUMMARY_MAP = {
    "Nu 50 tuoi, tien dai thao duong va beo phi do 1, dang theo chuong trinh thay doi loi song.": (
        "Nữ 50 tuổi, tiền đái tháo đường và béo phì độ 1, đang theo chương trình thay đổi lối sống."
    ),
    "Nam 61 tuoi, benh mach vanh sau dat stent, dang on dinh va tu tap di bo hang ngay.": (
        "Nam 61 tuổi, bệnh mạch vành sau đặt stent, đang ổn định và tự tập đi bộ hằng ngày."
    ),
    "Nu 40 tuoi, hoi chung ruot kich thich, trieu chung nang hon khi cang thang cong viec.": (
        "Nữ 40 tuổi, hội chứng ruột kích thích, triệu chứng nặng hơn khi căng thẳng công việc."
    ),
    "Nam 52 tuoi, gout man tinh, con dau tai phat khi an nhieu hai san va uong bia.": (
        "Nam 52 tuổi, gout mạn tính, cơn đau tái phát khi ăn nhiều hải sản và uống bia."
    ),
    "Nu 29 tuoi, thieu mau thieu sat sau sinh, than phien met moi khi cham con.": (
        "Nữ 29 tuổi, thiếu máu thiếu sắt sau sinh, than phiền mệt mỏi khi chăm con."
    ),
    "Nam 72 tuoi, benh than man giai doan 3 do tang huyet ap lau nam, theo doi sat chuc nang than.": (
        "Nam 72 tuổi, bệnh thận mạn giai đoạn 3 do tăng huyết áp lâu năm, theo dõi sát chức năng thận."
    ),
    "Nu 34 tuoi, suy giap nguyen phat, da dieu tri levothyroxine on dinh hon 1 nam.": (
        "Nữ 34 tuổi, suy giáp nguyên phát, đã điều trị levothyroxine ổn định hơn 1 năm."
    ),
    "Nam 45 tuoi, hen phe quan dai dang, hay kho tho ve dem khi troi lanh hoac gap khoi bui.": (
        "Nam 45 tuổi, hen phế quản dai dẳng, hay khó thở về đêm khi trời lạnh hoặc gặp khói bụi."
    ),
    "Nu 58 tuoi, roi loan lipid mau kem gan nhiem mo do nhe, da thay doi che do an nhung chua deu.": (
        "Nữ 58 tuổi, rối loạn lipid máu kèm gan nhiễm mỡ độ nhẹ, đã thay đổi chế độ ăn nhưng chưa đều."
    ),
    "Nam 67 tuoi, tang huyet ap va dai thao duong type 2 trong 8 nam, da tu theo doi huyet ap tai nha.": (
        "Nam 67 tuổi, tăng huyết áp và đái tháo đường type 2 trong 8 năm, đã tự theo dõi huyết áp tại nhà."
    ),
}

FACILITY_NAME_MAP = {
    "Benh vien Da khoa Pasteur Demo": "Bệnh viện Đa khoa Pasteur Demo",
}

RESTRICTIONS_MAP = {
    "Han che muoi duoi 5g/ngay, khong bo bua sang.": "Hạn chế muối dưới 5g/ngày, không bỏ bữa sáng.",
    "Han che do chien, tranh ruou bia.": "Hạn chế đồ chiên, tránh rượu bia.",
    "Tranh khoi thuoc la, giu am duong tho.": "Tránh khói thuốc lá, giữ ấm đường thở.",
    "Uong thuoc truoc an sang 30 phut.": "Uống thuốc trước ăn sáng 30 phút.",
    "Han che muoi va nuoc theo huong dan bac si.": "Hạn chế muối và nước theo hướng dẫn bác sĩ.",
    "Tang cuong thuc pham giau sat va vitamin C.": "Tăng cường thực phẩm giàu sắt và vitamin C.",
    "Tranh noi tang, han che bia ruou, uong du nuoc.": "Tránh nội tạng, hạn chế bia rượu, uống đủ nước.",
    "An thanh nhieu bua nho, han che do cay va caffeine.": "Ăn thành nhiều bữa nhỏ, hạn chế đồ cay và caffeine.",
    "Khong tu y ngung thuoc chong ket tap tieu cau.": "Không tự ý ngưng thuốc chống kết tập tiểu cầu.",
    "Giam duong nuoc ngot, tang van dong 150 phut/tuan.": "Giảm đường nước ngọt, tăng vận động 150 phút/tuần.",
}

CHRONIC_CONDITION_MAP = {
    "tang_huyet_ap": "tăng huyết áp",
    "dai_thao_duong_type_2": "đái tháo đường type 2",
    "roi_loan_lipid_mau": "rối loạn lipid máu",
    "gan_nhiem_mo": "gan nhiễm mỡ",
    "hen_phe_quan": "hen phế quản",
    "suy_giap": "suy giáp",
    "benh_than_man_gd3": "bệnh thận mạn giai đoạn 3",
    "thieu_mau_thieu_sat": "thiếu máu thiếu sắt",
    "gout_man_tinh": "gout mạn tính",
    "ibs": "hội chứng ruột kích thích",
    "benh_mach_vanh_sau_stent": "bệnh mạch vành sau đặt stent",
    "tien_dai_thao_duong": "tiền đái tháo đường",
    "beo_phi_do_1": "béo phì độ 1",
}

MEDICATION_FREQUENCY_MAP = {
    "sang": "sáng",
    "sang-toi": "sáng-tối",
    "toi": "tối",
    "2 lan/ngay": "2 lần/ngày",
    "khi can": "khi cần",
    "sang luc doi": "sáng lúc đói",
    "1 vien/ngay sau an": "1 viên/ngày sau ăn",
    "hang ngay": "hằng ngày",
}

MEDICAL_RECORD_STRING_MAP = {
    "quen thuoc 1-2 lan/tuan": "quên thuốc 1-2 lần/tuần",
    "nhuc dau nhe buoi sang": "nhức đầu nhẹ buổi sáng",
    "di bo 30 phut/ngay": "đi bộ 30 phút/ngày",
    "uống thuoc dung gio": "uống thuốc đúng giờ",
    "huyet ap < 140/90": "huyết áp < 140/90",
    "duong huyet doi < 7.0": "đường huyết đói < 7.0",
    "4 tuan": "4 tuần",
    "khong ro": "không rõ",
    "gan nhiem mo do 1": "gan nhiễm mỡ độ 1",
    "thap": "thấp",
    "giam do chien": "giảm đồ chiên",
    "ca bien 2 lan/tuan": "cá biển 2 lần/tuần",
    "di bo 150 phut/tuan": "đi bộ 150 phút/tuần",
    "8 tuan": "8 tuần",
    "nhe-den-vua": "nhẹ-đến-vừa",
    "nhe": "nhẹ",
    "giam": "giảm",
    "thinh thoang": "thỉnh thoảng",
    "can huong dan thao tac hit xit dung cach": "cần hướng dẫn thao tác hít xịt đúng cách",
    "on dinh": "ổn định",
    "giu lieu hien tai": "giữ liều hiện tại",
    "duoi 4g/ngay": "dưới 4g/ngày",
    "tang >1kg/24h": "tăng >1kg/24h",
}

RAG_CHUNK_STRING_MAP = {
    "Loai ban ghi": "Loại bản ghi",
    "Ngay": "Ngày",
    "Noi dung": "Nội dung",
    "Ho ten": "Họ tên",
    "Tom tat": "Tóm tắt",
    "Tom tat bo sung": "Tóm tắt bổ sung",
    "Benh nen": "Bệnh nền",
    "Thuoc dang dung": "Thuốc đang dùng",
    "Han che": "Hạn chế",
}

def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().split())


def conversation_title_from_message(content: str | None, created_at: str | None) -> str:
    normalized = normalize_text(content)
    if normalized:
        return normalized[:80]
    if created_at:
        return f"Cuộc trò chuyện {created_at}"
    return "Cuộc trò chuyện mới"


def normalize_chronic_conditions(value):
    if not isinstance(value, list):
        return value
    return [CHRONIC_CONDITION_MAP.get(str(item), str(item)) for item in value]


def normalize_current_medications(value):
    if not isinstance(value, list):
        return value
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        patched = dict(item)
        freq = normalize_text(str(patched.get("frequency", "")))
        if freq:
            patched["frequency"] = MEDICATION_FREQUENCY_MAP.get(freq, freq)
        normalized.append(patched)
    return normalized


def normalize_medical_record_content(value):
    if isinstance(value, str):
        normalized = normalize_text(value)
        return MEDICAL_RECORD_STRING_MAP.get(normalized, normalized)
    if isinstance(value, list):
        return [normalize_medical_record_content(item) for item in value]
    if isinstance(value, dict):
        return {k: normalize_medical_record_content(v) for k, v in value.items()}
    return value


def normalize_rag_chunk_content(value: str | None) -> str | None:
    if value is None:
        return value
    normalized = value
    for old, new in RAG_CHUNK_STRING_MAP.items():
        normalized = normalized.replace(old + ":", new + ":")
    for old, new in MEDICAL_RECORD_STRING_MAP.items():
        normalized = normalized.replace(old, new)
    for old, new in MEDICAL_SUMMARY_MAP.items():
        normalized = normalized.replace(old, new)
    for old, new in RESTRICTIONS_MAP.items():
        normalized = normalized.replace(old, new)
    for old, new in CHRONIC_CONDITION_MAP.items():
        normalized = normalized.replace(old, new)
    for old, new in MEDICATION_FREQUENCY_MAP.items():
        normalized = normalized.replace(old, new)
    for old, new in PATIENT_NAME_MAP.items():
        normalized = normalized.replace(old, new)
    return normalized


def main() -> None:
    updated_patients = 0
    updated_medical_summaries = 0
    updated_conversations = 0
    updated_medical_configs = 0
    updated_medical_records = 0
    updated_rag_chunks = 0

    with engine.begin() as conn:
        patient_rows = conn.execute(text("SELECT id, full_name, medical_summary FROM patients")).fetchall()
        for patient_id, full_name, medical_summary in patient_rows:
            current_name = normalize_text(full_name)
            next_name = full_name
            if current_name:
                normalized_name = PATIENT_NAME_MAP.get(current_name, current_name)
                if normalized_name != full_name:
                    next_name = normalized_name
                    updated_patients += 1

            current_summary = normalize_text(medical_summary)
            next_summary = medical_summary
            if current_summary:
                normalized_summary = MEDICAL_SUMMARY_MAP.get(current_summary, current_summary)
                if normalized_summary != medical_summary:
                    next_summary = normalized_summary
                    updated_medical_summaries += 1

            if next_name != full_name or next_summary != medical_summary:
                conn.execute(
                    text(
                        """
                        UPDATE patients
                        SET full_name = :name, medical_summary = :medical_summary
                        WHERE id = :id
                        """
                    ),
                    {"name": next_name, "medical_summary": next_summary, "id": patient_id},
                )

        conversation_rows = conn.execute(
            text(
                """
                SELECT c.id, c.title, c.created_at, m.content
                FROM conversations c
                LEFT JOIN LATERAL (
                    SELECT content
                    FROM messages
                    WHERE conversation_id = c.id AND role = 'USER'
                    ORDER BY created_at ASC
                    LIMIT 1
                ) m ON TRUE
                """
            )
        ).fetchall()

        for conversation_id, title, created_at, first_user_message in conversation_rows:
            current_title = normalize_text(title)
            if current_title and not current_title.lower().startswith("conversation "):
                continue

            next_title = conversation_title_from_message(
                first_user_message,
                created_at.strftime("%d/%m/%Y") if created_at else None,
            )
            if next_title != title:
                conn.execute(
                    text("UPDATE conversations SET title = :title WHERE id = :id"),
                    {"title": next_title, "id": conversation_id},
                )
                updated_conversations += 1

        config_rows = conn.execute(
            text(
                """
                SELECT id, facility_name, medical_summary, restrictions, chronic_conditions, current_medications
                FROM patient_medical_config
                """
            )
        ).fetchall()

        for config_id, facility_name, medical_summary, restrictions, chronic_conditions, current_medications in config_rows:
            current_facility = normalize_text(facility_name)
            current_summary = normalize_text(medical_summary)
            current_restrictions = normalize_text(restrictions)

            next_facility = FACILITY_NAME_MAP.get(current_facility, current_facility) if current_facility else facility_name
            next_summary = MEDICAL_SUMMARY_MAP.get(current_summary, current_summary) if current_summary else medical_summary
            next_restrictions = (
                RESTRICTIONS_MAP.get(current_restrictions, current_restrictions)
                if current_restrictions
                else restrictions
            )
            next_chronic = normalize_chronic_conditions(chronic_conditions)
            next_meds = normalize_current_medications(current_medications)

            if (
                next_facility != facility_name
                or next_summary != medical_summary
                or next_restrictions != restrictions
                or next_chronic != chronic_conditions
                or next_meds != current_medications
            ):
                conn.execute(
                    text(
                        """
                        UPDATE patient_medical_config
                        SET
                            facility_name = :facility_name,
                            medical_summary = :medical_summary,
                            restrictions = :restrictions,
                            chronic_conditions = CAST(:chronic_conditions AS jsonb),
                            current_medications = CAST(:current_medications AS jsonb)
                        WHERE id = :id
                        """
                    ),
                    {
                        "facility_name": next_facility,
                        "medical_summary": next_summary,
                        "restrictions": next_restrictions,
                        "chronic_conditions": json.dumps(next_chronic, ensure_ascii=False),
                        "current_medications": json.dumps(next_meds, ensure_ascii=False),
                        "id": config_id,
                    },
                )
                updated_medical_configs += 1

        medical_record_rows = conn.execute(
            text("SELECT id, content FROM medical_records")
        ).fetchall()
        for record_id, content in medical_record_rows:
            next_content = normalize_medical_record_content(content)
            if next_content != content:
                conn.execute(
                    text(
                        """
                        UPDATE medical_records
                        SET content = CAST(:content AS jsonb)
                        WHERE id = :id
                        """
                    ),
                    {"content": json.dumps(next_content, ensure_ascii=False), "id": record_id},
                )
                updated_medical_records += 1

        rag_chunk_rows = conn.execute(
            text("SELECT chunk_id, content FROM rag_chunks")
        ).fetchall()
        for chunk_id, content in rag_chunk_rows:
            next_content = normalize_rag_chunk_content(content)
            if next_content != content:
                conn.execute(
                    text(
                        """
                        UPDATE rag_chunks
                        SET content = :content
                        WHERE chunk_id = :chunk_id
                        """
                    ),
                    {"content": next_content, "chunk_id": chunk_id},
                )
                updated_rag_chunks += 1

    print(f"Updated patients.full_name: {updated_patients}")
    print(f"Updated patients.medical_summary: {updated_medical_summaries}")
    print(f"Updated conversations.title: {updated_conversations}")
    print(f"Updated patient_medical_config rows: {updated_medical_configs}")
    print(f"Updated medical_records rows: {updated_medical_records}")
    print(f"Updated rag_chunks rows: {updated_rag_chunks}")


if __name__ == "__main__":
    main()
