from chatops.services.request_normalizer import RequestNormalizerService


def test_request_normalizer_normalizes_common_product_synonyms_and_noise() -> None:
    service = RequestNormalizerService()

    normalized = service.normalize("어플 생성해줘ㅡ")

    assert normalized == "앱 생성해줘"


def test_request_normalizer_normalizes_common_project_shorthand() -> None:
    service = RequestNormalizerService()

    normalized = service.normalize("프젝 목록 보여줘")

    assert normalized == "프로젝트 목록 보여줘"
