"""Internal configuration, not additions to WP1 wire schemas."""
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Literal
from src.shared.validation import Contract, Positive, Nonnegative, MinorUnits, require, distinct

MANDATORY_FIELDS = ('title', 'maker_id', 'checker_id', 'department', 'objective',
                    'summary', 'start_date', 'end_date', 'budget_minor_units', 'currency')

STRATEGY_CRITERIA = (
    ("objective", "Mục tiêu", 15),
    ("audience", "Đối tượng", 15),
    ("channel", "Kênh", 15),
    ("timeline", "Thời gian", 15),
    ("kpi", "KPI", 15),
    ("budget_efficiency", "Hiệu quả ngân sách", 15),
    ("risk_control", "Kiểm soát rủi ro", 10),
)
STRATEGY_RUBRIC_V2_ID = "BA-STRATEGY-7"
STRATEGY_RUBRIC_V2_VERSION = "BA-STRATEGY-7-2.0"
STRATEGY_SCORE_ANCHOR_SCORES = (0, 25, 50, 75, 100)
STRATEGY_RUBRIC_V2_ANCHORS = {
    "objective": (
        (0, "Không có mục tiêu chiến dịch, hoặc chỉ yêu cầu duyệt hồ sơ."),
        (25, "Có mong muốn chung như tăng nhận diện hoặc bán hàng."),
        (50, "Nêu kết quả cần đạt và đối tượng hoặc sản phẩm liên quan."),
        (75, "Có kết quả định lượng, thời hạn và liên kết với KPI."),
        (100, "Đạt mức 75; có cơ sở giải thích mức mục tiêu, ưu tiên rõ và cách xác định thành công."),
    ),
    "audience": (
        (0, "Không xác định đối tượng hoặc nội dung không liên quan."),
        (25, "Chỉ nêu nhóm rộng như trẻ em hoặc mọi người."),
        (50, "Mô tả phân khúc và nhu cầu hoặc tình huống sử dụng."),
        (75, "Giải thích quan hệ giữa đối tượng, sản phẩm, thông điệp và cách tiếp cận."),
        (100, "Đạt mức 75; có căn cứ phù hợp hoặc kế hoạch kiểm chứng giả thuyết trước khi mở rộng."),
    ),
    "channel": (
        (0, "Không nêu kênh triển khai."),
        (25, "Có danh sách kênh nhưng chưa giải thích cách dùng."),
        (50, "Mô tả hoạt động hoặc nội dung trên từng kênh và quan hệ với đối tượng."),
        (75, "Nêu vai trò từng kênh, lời kêu gọi hành động và đường dẫn tới mục tiêu."),
        (100, "Đạt mức 75; có cách đo đóng góp từng kênh và nguyên tắc thử nghiệm, điều chỉnh."),
    ),
    "timeline": (
        (0, "Không có lịch hoặc có mâu thuẫn thời gian khiến kế hoạch không thể thực hiện."),
        (25, "Chỉ có ngày bắt đầu, ngày kết thúc hoặc tổng thời lượng."),
        (50, "Có các giai đoạn và đầu việc chính theo thứ tự hợp lý."),
        (75, "Có mốc bàn giao, người hoặc nhóm phụ trách và các phụ thuộc chính."),
        (100, "Đạt mức 75; có thời gian dự phòng và cách xử lý khi một mốc bị chậm."),
    ),
    "kpi": (
        (0, "Không có KPI hoặc chỉ số không liên quan đến mục tiêu."),
        (25, "Nêu tên chỉ số nhưng chưa có mức cần đạt."),
        (50, "Có mục tiêu số và khoảng thời gian đo."),
        (75, "Có định nghĩa chỉ số, nguồn dữ liệu hoặc công cụ và cách ghi nhận."),
        (100, "Đạt mức 75; có lịch kiểm tra, người phụ trách và ngưỡng dẫn tới hành động điều chỉnh."),
    ),
    "budget_efficiency": (
        (0, "Không có ngân sách sử dụng được hoặc số liệu mâu thuẫn nghiêm trọng chưa giải quyết."),
        (25, "Chỉ có tổng ngân sách."),
        (50, "Có phân bổ theo hạng mục hoặc kênh; tổng cộng khớp và phạm vi chi phí được nêu."),
        (75, "Có cơ sở tính các khoản chính: số lượng × đơn giá, báo giá hoặc giả định ghi rõ; liên kết chi phí với đầu ra."),
        (100, "Đạt mức 75; có cách kiểm soát chi phí, xử lý phát sinh và đánh giá hiệu quả hoặc quyết định tiếp tục hay dừng."),
    ),
    "risk_control": (
        (0, "Không nêu rủi ro và biện pháp xử lý."),
        (25, "Chỉ ghi chung như theo dõi hoặc xử lý khi có vấn đề."),
        (50, "Nêu rủi ro liên quan kế hoạch và biện pháp tương ứng."),
        (75, "Có người chịu trách nhiệm, dấu hiệu kích hoạt và phương án dự phòng."),
        (100, "Đạt mức 75; có ngưỡng dừng hoặc chuyển cấp, cách theo dõi và xử lý rủi ro còn lại."),
    ),
}
STRATEGY_REVIEW_ZERO_CRITERIA = ("objective", "audience", "channel", "timeline")
STRATEGY_REVIEW_MINIMUM_CRITERIA = ("kpi", "budget_efficiency", "risk_control")

MEDIA_EVIDENCE_KINDS = frozenset({
    "OCR_TEXT", "OBSERVATION", "OBJECT_DETECTION", "VISUAL_QUALITY", "VISUAL_INSPECTION",
})

RULE_IDS = (
    'INPUT_INTEGRITY', 'EVAL_VALID', 'MEDIA_PASS', 'MEDIA_CONFIDENCE',
    'FEASIBILITY_SCORE', 'FEASIBILITY_CONFIDENCE', 'BUDGET_LIMIT', 'AUTHORITY_LIMIT',
    'NO_HARD_VIOLATION', 'NO_EVIDENCE_CONFLICT', 'POLICY_ENABLED', 'PLAN_PENDING', 'ROUND_ACTIVE',
    'STRATEGY_REVIEW_GATES',
)
LEGACY_RULE_IDS = RULE_IDS[:-1]


@dataclass(frozen=True)
class Criterion(Contract):
    criterion_id: str
    maximum_score: Positive


@dataclass(frozen=True)
class MediaPolicyRule(Contract):
    rule_id: str
    severity: Literal["HARD_VIOLATION", "WARNING"]
    description: str
    required_evidence_kinds: tuple[str, ...]
    forbidden_literals: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value):
        # Existing scoped policies remain readable; literal checks are opt-in.
        if isinstance(value, Mapping) and "forbidden_literals" not in value:
            value = {**value, "forbidden_literals": []}
        return super().from_dict(value)

    def validate(self):
        require(bool(self.required_evidence_kinds), "Media policy rules need evidence requirements")
        require(set(self.required_evidence_kinds) <= MEDIA_EVIDENCE_KINDS,
                "Media policy has an unsupported evidence kind")
        distinct(self.required_evidence_kinds)
        distinct(self.forbidden_literals)
        require(all(isinstance(item, str) and item.strip() for item in self.forbidden_literals),
                "Media policy literal checks need nonblank text")
        if self.forbidden_literals:
            require("OCR_TEXT" in self.required_evidence_kinds,
                    "Forbidden literal checks require OCR_TEXT evidence")


@dataclass(frozen=True)
class MediaCompliancePolicy(Contract):
    policy_id: str
    policy_version: str
    status: Literal["ACTIVE", "DISABLED"]
    scope_departments: tuple[str, ...]
    scope_channels: tuple[str, ...]
    rules: tuple[MediaPolicyRule, ...]

    def validate(self):
        require(bool(self.scope_departments) and bool(self.scope_channels),
                "Media policy requires an explicit department and channel scope")
        require(bool(self.rules), "Media policy requires at least one configured rule")
        distinct(self.scope_departments)
        distinct(self.scope_channels)
        distinct([rule.rule_id for rule in self.rules])

    def applies_to(self, payload: dict) -> bool:
        department = payload.get("department")
        channels = payload.get("channels")
        if not isinstance(department, str) or not isinstance(channels, (list, tuple)):
            return False
        department_matches = "*" in self.scope_departments or department in self.scope_departments
        channel_matches = "*" in self.scope_channels or (
            bool(channels) and set(channels) <= set(self.scope_channels)
        )
        return department_matches and channel_matches


@dataclass(frozen=True)
class StrategyCriterion(Contract):
    criterion_id: str
    label: str
    weight: Positive
    score_anchors: tuple["StrategyScoreAnchor", ...] = ()

    @classmethod
    def from_dict(cls, value):
        if isinstance(value, Mapping) and "score_anchors" not in value:
            value = {**value, "score_anchors": []}
        return super().from_dict(value)


@dataclass(frozen=True)
class StrategyScoreAnchor(Contract):
    score: Literal[0, 25, 50, 75, 100]
    description: str


@dataclass(frozen=True)
class StrategyRubric(Contract):
    rubric_id: str
    rubric_version: str
    status: Literal["ACTIVE", "DISABLED"]
    criteria: tuple[StrategyCriterion, ...]

    @classmethod
    def from_dict(cls, value):
        if isinstance(value, Mapping):
            value = dict(value)
            is_v2 = value.get("rubric_id") == STRATEGY_RUBRIC_V2_ID and \
                value.get("rubric_version") == STRATEGY_RUBRIC_V2_VERSION
            criteria = value.get("criteria")
            if isinstance(criteria, (list, tuple)):
                hydrated = []
                for item in criteria:
                    if not isinstance(item, Mapping):
                        hydrated.append(item)
                        continue
                    item = dict(item)
                    if "score_anchors" not in item:
                        item["score_anchors"] = [
                            {"score": score, "description": description}
                            for score, description in STRATEGY_RUBRIC_V2_ANCHORS.get(
                                item.get("criterion_id"), ()
                            )
                        ] if is_v2 else []
                    hydrated.append(item)
                value["criteria"] = hydrated
        return super().from_dict(value)

    @property
    def criteria_by_id(self):
        return {criterion.criterion_id: criterion for criterion in self.criteria}

    @property
    def has_score_anchors(self):
        return self.rubric_id == STRATEGY_RUBRIC_V2_ID and \
            self.rubric_version == STRATEGY_RUBRIC_V2_VERSION

    def validate(self):
        distinct([criterion.criterion_id for criterion in self.criteria])
        configured = {criterion.criterion_id: criterion.weight for criterion in self.criteria}
        expected = {criterion_id: weight for criterion_id, _label, weight in STRATEGY_CRITERIA}
        require(configured == expected, "Strategy rubric must use the seven BA criteria and weights")
        require(sum(criterion.weight for criterion in self.criteria) == 100,
                "Strategy rubric weights must total 100")
        if self.has_score_anchors:
            require(set(configured) == set(STRATEGY_RUBRIC_V2_ANCHORS),
                    "Strategy rubric v2 must define every approved criterion anchor")
            for criterion in self.criteria:
                expected_anchors = STRATEGY_RUBRIC_V2_ANCHORS[criterion.criterion_id]
                actual_anchors = tuple((anchor.score, anchor.description)
                                       for anchor in criterion.score_anchors)
                require(actual_anchors == expected_anchors,
                        "Strategy rubric v2 anchors must match the approved version")
        else:
            require(not any(criterion.score_anchors for criterion in self.criteria),
                    "Scoring anchors require the approved Strategy rubric v2 version")


def strategy_checker_gate_failures(criterion_scores, critical_gaps=()):
    """Return the approved Strategy conditions that require human Checker review."""
    scores = {
        (item.get("criterion_id") if isinstance(item, Mapping) else item.criterion_id):
        (item.get("score") if isinstance(item, Mapping) else item.score)
        for item in criterion_scores
    }
    failures = [f"missing_{criterion_id}" for criterion_id, _label, _weight in STRATEGY_CRITERIA
                if criterion_id not in scores]
    failures.extend(criterion_id for criterion_id in STRATEGY_REVIEW_ZERO_CRITERIA
                    if scores.get(criterion_id) == 0)
    failures.extend(criterion_id for criterion_id in STRATEGY_REVIEW_MINIMUM_CRITERIA
                    if criterion_id in scores and scores[criterion_id] < 50)
    if critical_gaps:
        failures.append("unresolved_critical_gaps")
    return tuple(failures)


@dataclass(frozen=True)
class PolicySnapshot(Contract):
    snapshot_id: str
    policy_version: str
    auto_approval_policy_enabled: bool
    mandatory_fields: tuple[str, ...]
    criteria: tuple[Criterion, ...]
    known_model_versions: tuple[str, ...]
    allowed_media_types: tuple[str, ...]
    max_attachment_bytes: Positive
    rule_ids: tuple[str, ...] = RULE_IDS
    feasibility_threshold: Literal[70] = 70
    media_confidence_threshold: Literal[0.85] = .85
    feasibility_confidence_threshold: Literal[0.8] = .80

    def validate(self):
        require(self.rule_ids in (LEGACY_RULE_IDS, RULE_IDS), 'Required rules cannot be disabled')
        require(set(MANDATORY_FIELDS) <= set(self.mandatory_fields) and bool(self.criteria),
                'Incomplete policy')
        require(sum(c.maximum_score for c in self.criteria) == 100, 'Criteria must total 100')
        distinct(self.mandatory_fields)
        distinct([c.criterion_id for c in self.criteria])
        distinct(self.known_model_versions)


@dataclass(frozen=True)
class BudgetConfiguration(Contract):
    configuration_id: str
    currency: str
    precision: Nonnegative
    limit_minor_units: MinorUnits
    department: str
    active: bool


@dataclass(frozen=True)
class AuthoritySnapshot(Contract):
    snapshot_id: str
    currency: str
    auto_limit_minor_units: MinorUnits
    allowed_departments: tuple[str, ...]
    checker_id: str | None
    policy_owner_id: str | None
    budget_authority_id: str | None
    active: bool


@dataclass(frozen=True)
class ApprovalConfiguration(Contract):
    """Already effective configuration captured at submission, not a live selector."""
    policy: PolicySnapshot
    budgets: tuple[BudgetConfiguration, ...]
    authority: AuthoritySnapshot | None
    media_policy: MediaCompliancePolicy | None = None
    strategy_rubric: StrategyRubric | None = None
    media_model_snapshot: Any = None
    strategy_model_snapshot: Any = None

    def validate(self):
        if self.strategy_rubric is None:
            return
        configured = {criterion.criterion_id: criterion.weight
                      for criterion in self.strategy_rubric.criteria}
        policy_criteria = {criterion.criterion_id: criterion.maximum_score
                           for criterion in self.policy.criteria}
        require(configured == policy_criteria,
                "Approval policy and strategy rubric snapshots must use the same weights")

    @classmethod
    def from_dict(cls, value):
        # Policy snapshots persisted before Media/Strategy existed remain readable.
        if isinstance(value, Mapping) and set(value) == {"policy", "budgets", "authority"}:
            value = {**value, "media_policy": None, "strategy_rubric": None,
                     "media_model_snapshot": None, "strategy_model_snapshot": None}
        elif isinstance(value, Mapping) and set(value) == {
            "policy", "budgets", "authority", "media_policy", "strategy_rubric"
        }:
            value = {**value, "media_model_snapshot": None, "strategy_model_snapshot": None}
        return Contract.from_dict.__func__(cls, value)
