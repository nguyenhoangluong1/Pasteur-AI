"""Generate docs/benchmark_golden_vs_gemini_qwen_p011_p020.md from golden + pasted model outputs."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "golden_qa_p011_p020.md"
OUT = ROOT / "docs" / "benchmark_golden_vs_gemini_qwen_p011_p020.md"

# Answers from user-provided Gemini run (10 items per patient, P011..P020 order).
GEMINI: dict[str, list[str]] = {
    "P011": [
        "Chú bị COPD (Bệnh phổi tắc nghẽn mạn tính) mức độ trung bình.",
        "Thuốc Tiotropium (liều 18mcg, dùng 1 lần/ngày).",
        "Thuốc Salbutamol (100mcg).",
        "Ho khạc đờm nhiều vào buổi sáng và khó thở khi gắng sức.",
        "Tránh khói bụi và tập thở môi chúm (bên cạnh việc tiêm cúm hằng năm).",
        'Không cần, vì Salbutamol được chỉ định chỉ dùng "khi cần" (khi có cơn khó thở).',
        "Ưu tiên tuân thủ dùng Tiotropium hằng ngày, duy trì bài tập thở môi chúm và giữ môi trường sống tránh khói bụi.",
        "Cần ưu tiên các biện pháp bảo vệ (đeo khẩu trang chuyên dụng), hạn chế tối đa thời gian tiếp xúc và luôn mang theo thuốc Salbutamol dự phòng bên người.",
        "Không ổn. Tiotropium là thuốc kiểm soát duy trì, bắt buộc phải dùng hằng ngày để giữ cho đường thở luôn ổn định, không được tự ý bỏ.",
        "Dùng Tiotropium đều đặn mỗi ngày, xịt Salbutamol khi khó thở, tập thở môi chúm, tránh xa khói bụi và nhớ lịch tiêm cúm hằng năm.",
    ],
    "P012": [
        "Đau nửa đầu mạn tính (Migraine mạn).",
        "Thuốc Topiramate (25mg).",
        "Thuốc Sumatriptan (50mg).",
        "Cơn đau thường tăng lên khi cô bị thiếu ngủ hoặc gặp stress.",
        "Giữ giờ ngủ đều đặn và hạn chế uống cà phê sau 16h.",
        "Topiramate là thuốc uống cố định mỗi tối để phòng ngừa, trong khi Sumatriptan chỉ dùng để cắt cơn khi cơn đau xuất hiện.",
        "Tình trạng này sẽ làm cơn đau nửa đầu dễ bùng phát hoặc trở nên trầm trọng hơn.",
        "Ưu tiên nghỉ ngơi, uống thuốc Topiramate theo đúng lịch buổi tối. Nếu đau chuyển thành cơn đau nửa đầu rõ rệt, hãy dùng Sumatriptan.",
        "Không phù hợp. Hồ sơ đặc biệt lưu ý cô cần hạn chế cà phê sau 16h để tránh mất ngủ - tác nhân gây kích hoạt cơn đau.",
        "Uống Topiramate mỗi tối, dự phòng Sumatriptan khi lên cơn, kiểm soát stress, giữ lịch ngủ cố định và không uống cà phê sau 4 giờ chiều.",
    ],
    "P013": [
        "Rung nhĩ không do van tim và bệnh tăng huyết áp.",
        "Thuốc Apixaban (5mg).",
        "Thuốc Bisoprolol (2.5mg) và 1 liều Apixaban (vì Apixaban uống 2 lần/ngày).",
        "Có, chú có bệnh tăng huyết áp.",
        "Không được tự ý ngưng thuốc chống đông và phải cẩn thận tránh va chạm mạnh.",
        "Buổi sáng dùng Bisoprolol và Apixaban; cử thứ hai trong ngày tiếp tục dùng liều Apixaban còn lại.",
        "Tuyệt đối không. Việc tự ý ngưng thuốc chống đông cực kỳ nguy hiểm và trái với lưu ý của hồ sơ.",
        "Không được, chú không được tự ngưng thuốc chống đông dưới bất kỳ hình thức nào để tránh nguy cơ huyết khối.",
        'Ưu tiên thay đổi môn thể thao khác vì hồ sơ ghi rõ cần "tránh va chạm mạnh" nhằm hạn chế nguy cơ bầm tím hoặc xuất huyết do đang dùng thuốc chống đông.',
        "Tuân thủ nghiêm ngặt lịch uống Bisoprolol sáng và Apixaban 2 lần/ngày, tuyệt đối không tự ý ngưng thuốc chống đông và bảo vệ cơ thể khỏi va chạm mạnh.",
    ],
    "P014": [
        "Viêm khớp dạng thấp.",
        "Liều 10mg, dùng 1 lần/tuần.",
        "Uống (liều 5mg) vào ngày hôm sau của ngày uống Methotrexate.",
        "Triệu chứng cứng khớp buổi sáng kéo dài khoảng 45 phút.",
        "Cần theo dõi chỉ số men gan định kỳ.",
        "Tập vận động các khớp nhẹ nhàng.",
        "Methotrexate uống cố định 1 ngày trong tuần, Folic acid được uống tách ra vào đúng ngày liền kề sau đó.",
        'Không đúng, chỉ định bắt buộc là uống "hôm sau methotrexate".',
        "Không thể. Theo dõi men gan định kỳ là bắt buộc để kiểm soát tác dụng phụ của thuốc.",
        "Uống Methotrexate 1 lần/tuần, dùng Folic acid vào ngày hôm sau, chăm chỉ vận động khớp nhẹ nhàng mỗi ngày và tuân thủ xét nghiệm men gan định kỳ.",
    ],
    "P015": [
        "Bệnh trào ngược dạ dày thực quản (GERD).",
        "Thuốc Esomeprazole (40mg).",
        "Thuốc Gaviscon (10ml).",
        "Cảm giác nóng rát sau khi ăn tối.",
        "Không được nằm ngay sau khi ăn và cần kê cao đầu giường khi ngủ.",
        'Hoàn toàn không phù hợp, nó vi phạm lưu ý "không nằm ngay sau ăn".',
        "Buổi sáng dùng Esomeprazole trước khi ăn; sau các bữa ăn dùng Gaviscon.",
        "Uống Gaviscon sau bữa ăn tối, kiên quyết không nằm ngay sau đó và đảm bảo đầu giường đã được kê cao.",
        "Không được, Esomeprazole là thuốc điều trị nền tảng nhằm giảm tiết acid, không thể bỏ.",
        "Uống Esomeprazole sáng trước ăn và Gaviscon sau ăn, luôn nhớ kê cao đầu giường và tuyệt đối không nằm ngay sau khi ăn no.",
    ],
    "P016": [
        "Hội chứng buồng trứng đa nang (PCOS) và Tiền đái tháo đường.",
        "Dùng vào buổi tối (liều 500mg).",
        "Dùng 2 lần/ngày (liều 2g).",
        "Rối loạn kinh nguyệt và tình trạng tăng cân.",
        "Cần giảm các loại tinh bột nhanh.",
        "Tăng cường vận động một cách đều đặn.",
        "Uống Inositol 2 lần/ngày, Metformin XR mỗi tối kết hợp với việc giảm tinh bột nhanh và tăng cường vận động đều.",
        'Không đúng, hồ sơ yêu cầu phối hợp thuốc cùng với việc "giảm tinh bột nhanh".',
        'Chưa đủ, khuyến nghị là "vận động đều", cần duy trì thói quen rèn luyện thường xuyên hơn trong tuần.',
        "Tuân thủ lịch dùng Metformin XR buổi tối và Inositol 2 lần/ngày, đồng thời thực hiện giảm tinh bột nhanh và duy trì vận động đều đặn.",
    ],
    "P017": [
        "Suy tim (EF giảm nhẹ) và Bệnh mạch vành.",
        "Thuốc Sacubitril/Valsartan (49/51mg).",
        "Thuốc Spironolactone (25mg) và 1 liều Sacubitril/Valsartan.",
        "Phù chân vào cuối ngày.",
        "Hạn chế dưới 2g/ngày (<2g/ngày).",
        "Theo dõi cân nặng.",
        "(1) Uống thuốc đúng cữ (Spironolactone sáng, Sacubitril/Valsartan x2); (2) Ăn nhạt (muối <2g/ngày); (3) Cân để kiểm tra cân nặng mỗi buổi sáng.",
        'Rất sai. Việc ăn mặn vi phạm nguyên tắc "hạn chế muối <2g/ngày" và chính là nguyên nhân làm tình trạng phù nặng hơn.',
        "Không nên, việc theo dõi cân nặng mỗi sáng là thao tác then chốt để phát hiện sớm tình trạng ứ dịch.",
        "Uống thuốc tim mạch đầy đủ theo cữ, ăn thật nhạt (<2g muối mỗi ngày) và tạo thói quen kiểm tra cân nặng mỗi sáng.",
    ],
    "P018": [
        "Viêm da cơ địa.",
        "Thuốc kháng histamin Cetirizine (10mg).",
        "Hydrocortisone cream dùng để bôi lớp mỏng khi bệnh bùng phát.",
        "Triệu chứng ngứa tăng lên khi thời tiết hanh khô.",
        "Từ 2 đến 3 lần mỗi ngày.",
        "Tránh sử dụng các loại xà phòng có tính tẩy rửa mạnh.",
        "Nền: Dưỡng ẩm 2-3 lần/ngày, tránh xà phòng mạnh, uống Cetirizine tối. Bùng phát: Bôi thêm Hydrocortisone lớp mỏng.",
        "Không được. Dưỡng ẩm 2-3 lần/ngày là bước chăm sóc da bắt buộc phải duy trì liên tục để phòng ngừa bùng phát.",
        'Hoàn toàn không phù hợp, lời khuyên là bạn phải "tránh xà phòng mạnh".',
        "Duy trì dưỡng ẩm 2-3 lần/ngày, uống Cetirizine buổi tối, bôi Hydrocortisone khi viêm ngứa bùng phát và tránh xa xà phòng mạnh.",
    ],
    "P019": [
        "Tăng sinh lành tính tuyến tiền liệt (BPH).",
        "Thuốc Tamsulosin (0.4mg).",
        "Thuốc Finasteride (5mg).",
        "Tiểu đêm nhiều (khoảng 3 lần).",
        "Giảm uống nước sau 20h.",
        "Có, cần hạn chế cà phê vào buổi tối.",
        "Sáng uống Finasteride, tối uống Tamsulosin; từ sau 20h cần giảm lượng nước uống vào và hạn chế cà phê buổi tối.",
        'Không đúng, khuyến cáo chỉ rõ chú phải "giảm uống nước sau 20h".',
        "Không phù hợp, vì cà phê buổi tối sẽ kích thích bàng quang làm tình trạng tiểu đêm nặng hơn.",
        "Uống Finasteride buổi sáng, Tamsulosin buổi tối và tuyệt đối hạn chế nạp nước cũng như cà phê sau 8 giờ tối.",
    ],
    "P020": [
        "Bệnh loãng xương sau mãn kinh.",
        "Thuốc Alendronate (70mg, 1 lần/tuần).",
        "Uống 1 viên sau khi ăn trưa.",
        "Cô từng bị đau lưng do lún nhẹ đốt sống.",
        "Đi bộ chịu lực hằng ngày.",
        "Phòng ngừa té ngã.",
        "Uống Calcium+D3 sau khi ăn trưa, đi bộ chịu lực hằng ngày, luôn chú ý phòng ngừa té ngã và nhớ lịch uống Alendronate mỗi tuần 1 lần.",
        'Không đúng. Lời khuyên là cô vẫn cần duy trì "đi bộ chịu lực hằng ngày" để duy trì mật độ xương.',
        'Rất không ổn. Với tiền sử lún nhẹ đốt sống và bệnh loãng xương, việc "phòng ngừa té ngã" là nguyên tắc an toàn phải đặt lên hàng đầu trong mọi sinh hoạt.',
        "Uống Calcium+D3 sau bữa trưa, dùng Alendronate đúng lịch hằng tuần, đi bộ chịu lực mỗi ngày và đặc biệt cẩn thận phòng ngừa té ngã.",
    ],
}

QWEN: dict[str, list[str]] = {
    "P011": [
        "COPD mức trung bình.",
        "Tiotropium 18mcg, 1 lần/ngày.",
        "Salbutamol 100mcg, dùng khi khó thở.",
        "Ho khạc đờm nhiều buổi sáng, khó thở khi gắng sức.",
        "Tránh khói bụi; tiêm cúm hằng năm (hoặc tập thở môi chúm).",
        'Không — Salbutamol chỉ dùng "khi cần", không dùng dự phòng.',
        "Tập thở môi chúm hằng ngày + tránh tiếp xúc khói bụi.",
        "Đeo khẩu trang lọc bụi, hạn chế thời gian tiếp xúc, mang theo Salbutamol dự phòng.",
        "Không ổn — Tiotropium là thuốc duy trì, cần dùng đều để kiểm soát bệnh lâu dài, ngay cả khi triệu chứng tạm giảm.",
        "Dùng Tiotropium hằng ngày, Salbutamol khi khó thở, tránh khói bụi và tập thở môi chúm để kiểm soát COPD.",
    ],
    "P012": [
        "Đau nửa đầu mạn tính (migraine mạn).",
        "Topiramate 25mg.",
        "Sumatriptan 50mg.",
        "Khi thiếu ngủ và căng thẳng (stress).",
        "Giữ giờ ngủ đều đặn; hạn chế cà phê sau 16h.",
        'Topiramate dùng hằng ngày buổi tối để phòng ngừa; Sumatriptan chỉ dùng "khi cơn" để cắt cơn đau cấp.',
        "Ưu tiên điều chỉnh lại giấc ngủ, giảm stress để tránh kích hoạt cơn đau theo hồ sơ.",
        "Nghỉ ngơi ở nơi yên tĩnh, tối ánh sáng; nếu đau tăng thì dùng Sumatriptan 50mg theo chỉ định.",
        "Không phù hợp — hồ sơ khuyên hạn chế cà phê sau 16h để tránh ảnh hưởng giấc ngủ và kích hoạt migraine.",
        "Dùng Topiramate buổi tối để phòng ngừa, Sumatriptan khi có cơn; giữ ngủ đều và tránh cà phê sau 16h.",
    ],
    "P013": [
        "Rung nhĩ không do van tim.",
        "Apixaban 5mg.",
        "Bisoprolol 2.5mg.",
        "Tăng huyết áp.",
        "Không tự ngưng thuốc chống đông; tránh va chạm mạnh để giảm nguy cơ chảy máu.",
        "Apixaban 2 lần/ngày (sáng + tối); Bisoprolol 1 lần buổi sáng.",
        "Không — không tự ý dừng thuốc chống đông; nếu quên liều, liên hệ bác sĩ để được hướng dẫn bù liều an toàn.",
        "Tuyệt đối không — thuốc chống đông cần duy trì liên tục để phòng đột quỵ, chỉ ngưng khi có chỉ định bác sĩ.",
        "Tránh môn có nguy cơ va chạm mạnh; nếu bắt buộc, trang bị bảo hộ và thông báo cho người hướng dẫn về thuốc chống đông.",
        "Dùng Apixaban và Bisoprolol đều đặn, không tự ngưng thuốc chống đông, tránh va chạm mạnh để phòng biến cố tim mạch và chảy máu.",
    ],
    "P014": [
        "Viêm khớp dạng thấp.",
        "10mg, 1 lần/tuần (ngày cố định trong tuần).",
        "Uống 5mg vào ngày sau khi dùng Methotrexate.",
        "Cứng khớp khoảng 45 phút.",
        "Men gan (do Methotrexate có thể ảnh hưởng gan).",
        "Tập vận động khớp nhẹ để duy trì tầm vận động.",
        "Methotrexate: 1 lần/tuần; Folic acid: uống hôm sau Methotrexate để giảm tác dụng phụ.",
        "Không đúng — Folic acid nên uống ngày sau để tối ưu hiệu quả bảo vệ và giảm độc tính của Methotrexate.",
        "Không — Methotrexate vẫn có nguy cơ ảnh hưởng gan dù triệu chứng khớp cải thiện, cần theo dõi định kỳ.",
        "Dùng Methotrexate 1 lần/tuần kèm Folic acid ngày sau, theo dõi men gan định kỳ và tập vận động khớp nhẹ hằng ngày.",
    ],
    "P015": [
        "Trào ngược dạ dày thực quản (GERD).",
        "Esomeprazole 40mg.",
        "Gaviscon 10ml.",
        "Nóng rát sau ăn tối.",
        "Không nằm ngay sau ăn; kê cao đầu giường khi ngủ.",
        "Không — nên đợi ít nhất 2-3 giờ sau ăn mới nằm để giảm trào ngược.",
        "Esomeprazole: sáng trước ăn; Gaviscon: sau các bữa ăn (đặc biệt sau ăn tối).",
        "Kiểm tra lại tư thế sau ăn (không nằm ngay), dùng Gaviscon sau ăn tối, kê cao đầu giường.",
        "Không nên — Esomeprazole là thuốc điều trị nền giảm tiết acid, Gaviscon chỉ hỗ trợ triệu chứng tức thời.",
        "Dùng Esomeprazole buổi sáng trước ăn, Gaviscon sau ăn, không nằm ngay sau ăn và kê cao đầu giường để kiểm soát trào ngược.",
    ],
    "P016": [
        "Hội chứng buồng trứng đa nang (PCOS) và tiền đái tháo đường.",
        "Buổi tối.",
        "2 lần/ngày.",
        "Rối loạn kinh nguyệt và tăng cân.",
        "Giảm tinh bột nhanh (đường, bánh kẹo, đồ uống có gas).",
        "Tăng vận động đều đặn, hằng ngày.",
        "Metformin XR buổi tối + Inositol 2 lần/ngày; giảm tinh bột nhanh + vận động đều.",
        "Không đúng — quản lý PCOS và tiền đái tháo đường cần kết hợp thuốc + điều chỉnh chế độ ăn để đạt hiệu quả tối ưu.",
        "Không đủ — khuyến nghị là vận động đều đặn hằng ngày để cải thiện đề kháng insulin và kiểm soát cân nặng.",
        "Dùng Metformin XR và Inositol đều đặn, kết hợp giảm tinh bột nhanh và vận động hằng ngày để quản lý PCOS và tiền đái tháo đường.",
    ],
    "P017": [
        "Suy tim EF giảm nhẹ và bệnh mạch vành.",
        "Sacubitril/Valsartan 49/51mg.",
        "Spironolactone 25mg.",
        "Phù chân cuối ngày.",
        "<2g/ngày.",
        "Cân nặng (để phát hiện sớm giữ nước).",
        "(1) Dùng thuốc đúng lịch; (2) Hạn chế muối <2g/ngày; (3) Theo dõi cân nặng mỗi sáng.",
        "Không phù hợp — ăn mặn làm tăng giữ nước, làm nặng thêm phù và suy tim.",
        "Không nên — cân nặng thay đổi đột ngột là dấu hiệu sớm của giữ nước trong suy tim, giúp can thiệp kịp thời.",
        "Dùng Sacubitril/Valsartan và Spironolactone đều đặn, hạn chế muối <2g/ngày và theo dõi cân nặng mỗi sáng để kiểm soát suy tim.",
    ],
    "P018": [
        "Viêm da cơ địa.",
        "Cetirizine 10mg.",
        "Hydrocortisone cream: bôi mỏng khi bùng phát triệu chứng.",
        "Thời tiết hanh khô.",
        "2-3 lần/ngày.",
        "Xà phòng mạnh, chất tẩy rửa gây kích ứng da.",
        "Nền: dưỡng ẩm 2-3 lần/ngày + tránh xà phòng mạnh; Bùng phát: bôi Hydrocortisone cream mỏng + tiếp tục dưỡng ẩm.",
        "Không — dưỡng ẩm là nền tảng duy trì hàng rào bảo vệ da, giúp ngăn ngừa bùng phát ngay cả khi da đang ổn.",
        "Không — xà phòng mạnh làm khô da, phá vỡ hàng rào bảo vệ và làm nặng thêm viêm da cơ địa.",
        "Dùng Cetirizine buổi tối, dưỡng ẩm 2-3 lần/ngày, tránh xà phòng mạnh và bôi Hydrocortisone khi bùng phát để kiểm soát viêm da cơ địa.",
    ],
    "P019": [
        "Tăng sinh lành tính tuyến tiền liệt (BPH).",
        "Tamsulosin 0.4mg.",
        "Finasteride 5mg.",
        "Tiểu đêm 3 lần.",
        "Giảm uống nước sau 20h.",
        "Có — hạn chế cà phê buổi tối vì caffeine làm tăng sản xuất nước tiểu.",
        "Tamsulosin buổi tối + Finasteride buổi sáng; giảm uống nước sau 20h + hạn chế cà phê buổi tối để giảm tiểu đêm.",
        "Không đúng — nên giảm uống nước sau 20h để hạn chế tiểu đêm theo khuyến nghị hồ sơ.",
        "Không phù hợp — cà phê buổi tối làm tăng tần suất tiểu đêm, ảnh hưởng chất lượng giấc ngủ.",
        "Dùng Tamsulosin buổi tối và Finasteride buổi sáng, kết hợp giảm uống nước và cà phê sau 20h để cải thiện tiểu đêm.",
    ],
    "P020": [
        "Loãng xương sau mãn kinh.",
        "Alendronate 70mg.",
        "1 viên sau ăn trưa.",
        "Từng đau lưng do lún nhẹ đốt sống.",
        "Đi bộ chịu lực hằng ngày.",
        "Phòng ngừa té ngã (vì loãng xương làm tăng nguy cơ gãy xương).",
        "Alendronate 1 lần/tuần (uống đúng cách: sáng sớm, lúc đói, ngồi thẳng 30 phút); Calcium+D3 sau ăn trưa; đi bộ chịu lực hằng ngày + phòng ngừa té ngã.",
        "Không đúng — đi bộ chịu lực giúp tăng mật độ xương và giảm nguy cơ lún đốt sống; nên bắt đầu nhẹ nhàng và tăng dần dưới hướng dẫn.",
        "Không ổn — nguy cơ té ngã và gãy xương vẫn cao ở người loãng xương, cần duy trì biện pháp phòng ngừa liên tục.",
        "Dùng Alendronate hằng tuần và Calcium+D3 sau ăn trưa, kết hợp đi bộ chịu lực hằng ngày và phòng ngừa té ngã để bảo vệ xương.",
    ],
}


def parse_golden(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    header_re = re.compile(r"^##\s+(P\d{3})\s*-\s*(.+)$")
    line_re = re.compile(r"^- \[Tier (\d)\] Q:\s*(.*?)\s*\|\s*A_ref:\s*(.*)$")
    rows: list[dict] = []
    current_code = None
    current_name = None
    for line in text.splitlines():
        line = line.strip()
        mh = header_re.match(line)
        if mh:
            current_code, current_name = mh.group(1), mh.group(2)
            continue
        mq = line_re.match(line)
        if mq and current_code:
            rows.append(
                {
                    "patient_code": current_code,
                    "patient_name": current_name,
                    "tier": int(mq.group(1)),
                    "question": mq.group(2).strip(),
                    "reference_answer": mq.group(3).strip(),
                }
            )
    return rows


def main() -> None:
    golden_rows = parse_golden(GOLDEN)
    assert len(golden_rows) == 100, len(golden_rows)

    combined: list[dict] = []
    for row in golden_rows:
        code = row["patient_code"]
        idx = sum(1 for r in combined if r["patient_code"] == code) + 1
        g_list = GEMINI[code]
        q_list = QWEN[code]
        if idx > 10 or idx < 1:
            raise RuntimeError(code)
        combined.append(
            {
                **row,
                "question_index": idx,
                "answer_gemini": g_list[idx - 1],
                "answer_qwen": q_list[idx - 1],
            }
        )

    lines: list[str] = [
        "# So sánh đáp án: Golden vs Gemini vs Qwen (P011–P020)",
        "",
        "File này gom **100 câu** (cùng thứ tự với `docs/golden_qa_p011_p020.md`).",
        "",
        "- **Đáp án chuẩn (reference):** lấy từ `docs/golden_qa_p011_p020.md` — không nhân đôi trong repo; khi chấm điểm chỉ cần **2 file**: golden + file này.",
        "- **Gemini / Qwen:** bản ghi một lần chạy do người dùng cung cấp (đã chuẩn hóa vào bảng + JSON bên dưới).",
        "",
        "Cập nhật lại đáp án model: sửa `scripts/build_benchmark_compare_md.py` (dict `GEMINI` / `QWEN`) rồi chạy:",
        "",
        "```bash",
        "python scripts/build_benchmark_compare_md.py",
        "```",
        "",
        "---",
        "",
    ]

    current: str | None = None
    for row in combined:
        if row["patient_code"] != current:
            current = row["patient_code"]
            lines.append(f"## {current} — {row['patient_name']}")
            lines.append("")
            lines.append("| # | Tier | Câu hỏi | Chuẩn (golden) | Gemini | Qwen |")
            lines.append("|---:|---:|---|---|---|---|")
        i = row["question_index"]
        t = row["tier"]
        q = row["question"].replace("|", "\\|")
        ref = row["reference_answer"].replace("|", "\\|")
        ag = row["answer_gemini"].replace("|", "\\|").replace("\n", " ")
        aq = row["answer_qwen"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {i} | {t} | {q} | {ref} | {ag} | {aq} |")
        if i == 10:
            lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Import nhanh (JSON)",
            "",
            "Parse khối dưới trong Python: `json.loads(...)` — mỗi phần tử có đủ `question`, `reference_answer`, `answer_gemini`, `answer_qwen`, `tier`, `patient_code`.",
            "",
            "```json",
            json.dumps(combined, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({len(combined)} rows)")


if __name__ == "__main__":
    main()
