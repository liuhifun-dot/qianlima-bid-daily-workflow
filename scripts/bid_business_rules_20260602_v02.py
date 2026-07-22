# -*- coding: utf-8 -*-
"""
TPK 标讯业务边界与投标经理式复判规则。

目标不是用关键词直接替代判断，而是把关键词降级为证据：
- 范围词用于召回机会。
- 排除词必须结合项目本体上下文。
- 标题不清楚但可能有业务机会时进入 C 级人工复核。
"""

from __future__ import annotations

import re

from dataclasses import dataclass, asdict
from typing import Iterable


IN_SCOPE_STRONG = [
    "路灯", "道路照明", "照明工程", "户外照明", "亮化", "亮化工程",
    "景观亮化", "夜景亮化", "建筑照明", "园林景观亮化", "智慧路灯",
    "太阳能路灯", "洗墙灯", "线条灯", "投光灯",
    "景观灯", "庭院灯", "草坪灯", "点光源", "地埋灯", "埋地灯",
]

# 标题含照明/路灯/亮化/光伏/充电桩但边界不清的关键词
# 这些词出现在标题时不能直接排除，必须正文复判或待人工复核
AMBIGUOUS_TITLE_LIGHTING = [
    "照明", "路灯", "亮化", "光伏", "充电桩",
    "灯具", "LED", "灯光", "灯饰", "光源",
]

IN_SCOPE_PRODUCTS = [
    "LED洗墙灯", "LED线条灯", "LED投光灯", "LED路灯", "LED太阳能路灯",
    "景观灯", "庭院灯", "草坪灯", "LED点光源", "LED地埋灯", "LED埋地灯",
]

IN_SCOPE_CONSTRUCTION = [
    "户外照明工程", "路灯工程", "道路照明工程", "照明工程施工",
    "路灯工程施工", "道路照明工程施工", "亮化改造", "建筑照明改造",
    "户外建筑照明", "分布式光伏", "光伏施工", "光伏发电安装",
    "光伏发电建设", "光伏发电项目", "光伏发电项目施工",
]

BROAD_RECALL = [
    "老旧城区改造", "老旧小区改造", "街道提升", "道路提升", "道路改造",
    "市政道路", "市政工程", "基础设施改造", "城市更新", "品质提升",
    "环境提升", "风貌提升", "美丽圩镇", "圩镇提升", "公园改造",
    "园林景观", "景观工程", "文旅夜景", "夜游", "场馆改造",
]

ROAD_CIVIL_DOMINANT = [
    "村道硬底化", "道路硬底化", "硬底化", "路面拓宽", "道路拓宽",
    "路面硬化", "道路硬化", "巷道硬化", "沥青摊铺", "水泥路面",
    "道路黑化", "路面改造", "道路改扩建",
]

GENERIC_LIGHTING = ["灯具采购", "灯具", "节能灯具", "照明灯具"]

OUTDOOR_CONTEXT = [
    "户外", "道路", "市政", "公园", "园林", "景观", "亮化", "夜景",
    "建筑外立面", "外立面", "广场", "街道", "路灯", "庭院", "草坪",
]

INDOOR_CONTEXT = [
    "图书馆", "教室", "办公室", "实验室", "宿舍", "病房", "室内",
    "教学楼", "办公楼", "楼内", "会议室",
]

MAINTENANCE_WORDS = ["维护", "维修", "养护", "运维", "更换", "改造"]

PV_MAINTENANCE_POSITIVE_WORDS = [
    "光伏发电项目", "分布式光伏", "光伏改造", "光伏扶贫", "光伏组件洗板",
    "光伏电缆", "光伏支架", "PVC管", "抗风绳", "拆装", "更换", "维护",
]

PV_MAINTENANCE_EVIDENCE_WORDS = [
    "施工工期", "工期", "工程预算", "工程预算审核", "施工企业", "安全生产许可证",
    "承装", "承修", "承试", "安装", "拆装", "光伏电缆", "PVC管", "抗风绳",
]

SERVICE_EXCLUDE = [
    "检验监测", "检测监测", "检验检测", "检测校验", "校验辅助服务", "检验服务", "检测服务",
    "工程检测", "第三方检测", "质量检测", "监测服务", "竣工检测",
    "监理服务", "工程监理", "施工监理", "监理招标", "设计服务",
    "工程设计", "勘察服务", "工程勘察", "勘察设计", "初步设计",
    "详细勘察", "设计招标", "咨询服务", "工程咨询",
    "造价咨询", "造价预算", "预算编制", "全过程咨询", "全过程工程咨询",
    "环境影响评价", "建设项目环境影响评价", "环评",
    "测绘服务", "竣工测绘", "能源审计", "节能技术服务", "安全影响评估",
    "安全评估", "资产评估", "评估中介", "评估中介机构", "选聘资产评估", "地震安全性评价", "地震安评", "安评报告", "安全性评价", "评价机构",
    "监理", "监理公告", "检测与监测", "智能检测", "监测产教融合", "产教融合实训", "实训基地",
    "监控系统运维", "道路监控系统", "道路监控", "视频监控", "会务服务", "活动服务", "广告物料", "仪式服务", "直播服务",
    "可行性研究", "施工图审查", "图审", "审查服务", "第三方监测",
    "第三方监测服务", "测量服务", "核实测量", "规划放线", "工程规划放线",
    "照明设计项目", "照明设计服务", "照明专项设计", "纯咨询设计",
    "售后回租", "融资租赁", "值班用房租赁", "用房租赁", "房屋租赁",
    "场地租赁", "物业租赁", "机械租赁", "设备租赁", "车辆租赁",
]

PRODUCT_EXCLUDE = [
    "光伏板采购", "太阳能板采购", "光伏组件采购", "光伏物资采购",
    "标的物光伏组件", "光伏组件", "组件采购",
    "充电桩", "储能柜", "储能系统", "变压器", "配电系统", "配电工程",
    "配电柜", "EPS主机柜", "事故照明装置", "备件采购", "应急照明备件", "空调维修", "空调维保", "电梯工程", "电梯维保",
    "智慧校园", "交通杆", "交通信号杆", "消防工程", "消防系统",
    "消防设施", "暖通工程", "消防维保",
]

PURE_PRODUCT_TITLE_REJECT = [
    "光伏物资采购", "标的物光伏组件", "光伏组件采购", "光伏组件",
]

NON_LIGHTING_MAIN_REJECT = [
    "石材采购", "石材", "铺装工程", "健身器材", "雕塑采购",
    "水圳", "水渠", "水利渠", "桥梁加固", "桥梁升级改造", "结构加固",
]

NON_LIGHTING_MAIN_AMBIGUOUS = [
    "基础设施补短板", "补短板", "道路养护", "道路提升", "道路改造",
    "学校路养护", "养护提升", "农田水利", "河道修缮", "管道灌溉",
    "产业和基础设施", "路面", "道路", "巷道", "停车场", "广场道路",
]

DISPLAY_ONLY = [
    "LED显示屏", "LED大屏", "显示屏采购", "显示系统", "LED显示",
    "LED屏", "屏采购", "护目灯", "显示屏",
]

BODY_SCOPE_LABELS = [
    "项目名称", "采购项目名称", "工程名称", "项目概述", "采购内容",
    "服务内容", "招标范围", "采购范围", "建设内容", "工作内容",
    "标的名称", "合同主要内容", "发包工作内容",
]

PAGE_TAIL_MARKERS = [
    "\n招标项目商机\n",
    "\n数据纠错\n",
    "\nTEL\n千里马咨询电话",
    "\n潮州招标网\n",
    "\n相关推荐\n",
]


@dataclass
class BusinessJudgment:
    recommendation_level: str
    decision: str
    project_type: str
    business_direction: str
    doable_scope: str
    judgment_reason: str
    needs_vip_text: bool
    manual_review_reason: str
    scope_hits: list[str]
    product_hits: list[str]
    construction_hits: list[str]
    broad_recall_hits: list[str]
    exclude_hits: list[str]
    display_hits: list[str]
    maintenance_hits: list[str]
    risk_points: list[str]
    evidence: list[dict[str, str]]

    def to_dict(self):
        return asdict(self)


def trim_qianlima_text(text: str) -> str:
    if not text:
        return ""
    positions = [text.find(marker) for marker in PAGE_TAIL_MARKERS if text.find(marker) > 200]
    if positions:
        return text[:min(positions)]
    return text


def hits(text: str, keywords: Iterable[str]) -> list[str]:
    return [kw for kw in keywords if kw and kw in text]


def snippet_for(text: str, keyword: str, size: int = 70) -> str:
    if not keyword or keyword not in text:
        return ""
    idx = text.find(keyword)
    start = max(0, idx - size)
    end = min(len(text), idx + len(keyword) + size)
    return text[start:end].replace("\n", " ").strip()


def is_footer_or_company_noise(window: str, keyword: str) -> bool:
    if "咨询电话" in window or "客服电话" in window:
        return True
    if "有限公司" in window and keyword in {"工程咨询", "造价咨询", "全过程咨询", "咨询服务"}:
        return True
    return False


def is_background_service_noise(window: str, keyword: str) -> bool:
    """Ignore service words that describe project governance, not the tender object."""
    if "监理" not in keyword:
        return False
    compact = re.sub(r"\s+", "", window)
    background_patterns = (
        "监理人发出的开工通知",
        "监理单位",
        "本招标项目的监理人",
        "与本招标项目的监理人",
        "为本招标项目的监理人",
        "监理工程师签发",
        "监理机构",
        "禁止投标条款",
    )
    return any(pattern in compact for pattern in background_patterns)


def contextual_exclude_hits(title_preview: str, body_text: str) -> list[str]:
    combined = f"{title_preview}\n{body_text}"
    title_only = title_preview.split("\n", 1)[0]
    found = []
    for kw in SERVICE_EXCLUDE + PRODUCT_EXCLUDE:
        start = 0
        while True:
            idx = combined.find(kw, start)
            if idx < 0:
                break
            window = combined[max(0, idx - 90): idx + len(kw) + 90]
            in_title = idx < len(title_only)
            if in_title:
                found.append(kw)
                break
            if is_footer_or_company_noise(window, kw):
                start = idx + len(kw)
                continue
            if is_background_service_noise(window, kw):
                start = idx + len(kw)
                continue
            in_body_scope = any(label in window for label in BODY_SCOPE_LABELS)
            if in_body_scope:
                found.append(kw)
                break
            start = idx + len(kw)
    return found


def build_evidence(text: str, keywords: Iterable[str], limit: int = 8) -> list[dict[str, str]]:
    evidence = []
    seen = set()
    for kw in keywords:
        if kw in seen:
            continue
        seen.add(kw)
        snippet = snippet_for(text, kw)
        if snippet:
            evidence.append({"keyword": kw, "snippet": snippet})
        if len(evidence) >= limit:
            break
    return evidence


def infer_project_type(text: str) -> str:
    if any(w in text for w in ["施工", "工程", "建设", "改造", "安装", "维修", "维护"]):
        return "工程"
    if any(w in text for w in ["采购", "供货", "设备", "灯具"]):
        return "货物"
    if any(w in text for w in ["服务", "咨询", "监理", "检测", "测绘", "审计"]):
        return "服务"
    return "不确定"


def classify_business_opportunity(
    *,
    title: str,
    preview: str = "",
    body_text: str = "",
    vip_status: str = "",
    screening_exclude_reason: str = "",
) -> BusinessJudgment:
    title = title or ""
    preview = preview or ""
    body_text = trim_qianlima_text(body_text or "")
    title_preview = f"{title}\n{preview}".strip()
    full_text = f"{title_preview}\n{body_text}".strip()

    title_lighting = hits(title, IN_SCOPE_STRONG + IN_SCOPE_PRODUCTS + IN_SCOPE_CONSTRUCTION)
    road_civil = hits(title, ROAD_CIVIL_DOMINANT)
    non_lighting_reject = hits(title_preview, NON_LIGHTING_MAIN_REJECT)
    non_lighting_ambiguous = hits(title_preview, NON_LIGHTING_MAIN_AMBIGUOUS)
    scope = hits(full_text, IN_SCOPE_STRONG)
    products = hits(full_text, IN_SCOPE_PRODUCTS)
    construction = hits(full_text, IN_SCOPE_CONSTRUCTION)
    broad = hits(full_text, BROAD_RECALL)
    generic_lighting = hits(full_text, GENERIC_LIGHTING)
    outdoor_context = hits(full_text, OUTDOOR_CONTEXT)
    indoor_context = hits(full_text, INDOOR_CONTEXT)
    display = hits(full_text, DISPLAY_ONLY)
    maintenance = hits(full_text, MAINTENANCE_WORDS)
    excludes = contextual_exclude_hits(title_preview, body_text)
    project_type = infer_project_type(full_text)
    body_ok = bool(body_text.strip()) and vip_status == "ok"

    risk_points = []
    manual_reason = ""
    business_direction = "不确定"
    doable_scope = ""

    if screening_exclude_reason:
        risk_points.append(f"初筛排除记录: {screening_exclude_reason}")

    # 道路硬化/拓宽是土建道路主标的；如果标题没有明确照明/路灯/亮化主标的，
    # 正文或清单中零星出现“新建路灯”不能把整个项目升级为可跟进项目。
    if road_civil and not title_lighting:
        reason = f"项目主标的是道路硬化/拓宽土建工程: {', '.join(road_civil[:5])}"
        return BusinessJudgment(
            recommendation_level="D",
            decision="reject",
            project_type=project_type,
            business_direction="道路土建硬化/拓宽",
            doable_scope="",
            judgment_reason=reason,
            needs_vip_text=False,
            manual_review_reason="",
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=road_civil + excludes,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points,
            evidence=build_evidence(full_text, road_civil + scope + broad),
        )

    # 服务类硬排除优先级最高，即使标题含路灯也可能只是审计/监理/检测服务。
    # 服务类硬排除：只对真实服务词立即排除；如果标题本身明确是照明/路灯/灯具/亮化工程，
    # 不允许因为医院、学校、道路等场景词被误杀。
    service_hits = [kw for kw in excludes if kw in SERVICE_EXCLUDE]
    hard_service_hits = [
        kw for kw in service_hits
        if any(token in kw for token in [
            "监理", "检测", "检验", "设计", "咨询", "评估", "测绘", "勘察",
            "租赁", "审计", "评价", "安评", "环评", "代维", "运维"
        ])
    ]
    if hard_service_hits:
        reason = f"项目本体为不可做服务: {', '.join(hard_service_hits[:5])}"
        return BusinessJudgment(
            recommendation_level="D",
            decision="reject",
            project_type=project_type,
            business_direction="不可做服务",
            doable_scope="",
            judgment_reason=reason,
            needs_vip_text=False,
            manual_review_reason="",
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=excludes,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points,
            evidence=build_evidence(full_text, hard_service_hits + scope + products + broad),
        )
    if service_hits and not title_lighting:
        reason = f"服务类或非施工类语境，且标题没有明确照明/路灯/亮化/光伏施工业务证据: {', '.join(service_hits[:5])}"
        return BusinessJudgment(
            recommendation_level="D",
            decision="reject",
            project_type=project_type,
            business_direction="不可做服务",
            doable_scope="",
            judgment_reason=reason,
            needs_vip_text=False,
            manual_review_reason="",
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=excludes,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points,
            evidence=build_evidence(full_text, service_hits + scope + products + broad),
        )

    product_excludes = [kw for kw in excludes if kw in PRODUCT_EXCLUDE]
    pure_product_title = hits(title_preview, PURE_PRODUCT_TITLE_REJECT)
    construction_action_in_title = any(
        word in title for word in ["施工", "安装", "总承包", "建设", "改造", "PC总承包", "EPC"]
    )
    if pure_product_title and not construction_action_in_title:
        reason = f"项目主标的是光伏物资/组件采购，不是光伏施工安装: {', '.join(pure_product_title[:5])}"
        return BusinessJudgment(
            recommendation_level="D",
            decision="reject",
            project_type=project_type,
            business_direction="光伏物资/组件采购",
            doable_scope="",
            judgment_reason=reason,
            needs_vip_text=False,
            manual_review_reason="",
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=product_excludes + pure_product_title,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points,
            evidence=build_evidence(full_text, pure_product_title + product_excludes + construction),
        )

    # 纯 LED 显示屏供货不做；如果同时有路灯/亮化主范围，进入 C 级人工判断主次。
    if display and not (scope or products or construction):
        return BusinessJudgment(
            recommendation_level="D",
            decision="reject",
            project_type=project_type,
            business_direction="纯LED显示屏/显示系统",
            doable_scope="",
            judgment_reason="纯 LED 显示屏/显示系统供货不属于当前业务范围",
            needs_vip_text=False,
            manual_review_reason="",
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=excludes,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points,
            evidence=build_evidence(full_text, display),
        )
    if display and (scope or construction):
        risk_points.append("含 LED 显示屏词，同时含照明/亮化/路灯范围，需要判断主标的")

    # 纯产品/系统排除。如果同时有明确可做照明主范围，降为 C，避免误杀附带内容。
    if product_excludes and not (scope or products or construction):
        reason = f"项目本体命中不可做产品/系统: {', '.join(product_excludes[:5])}"
        return BusinessJudgment(
            recommendation_level="D",
            decision="reject",
            project_type=project_type,
            business_direction="不可做产品/系统",
            doable_scope="",
            judgment_reason=reason,
            needs_vip_text=False,
            manual_review_reason="",
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=excludes,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points,
            evidence=build_evidence(full_text, product_excludes + scope + products + broad),
        )
    if product_excludes:
        risk_points.append(f"含不可做附带项，需判断主次: {', '.join(product_excludes[:5])}")

    # 人工判断的关键区别：先看“采购/施工主标的”，再看正文里是否附带照明词。
    # 如果标题或采购内容已经说明主标的是石材、铺装、道路养护、补短板等，
    # 正文中零星出现照明/路灯，不能升级为推荐项目。
    if not title_lighting and non_lighting_reject:
        reason = f"项目主标的是非照明采购/工程: {', '.join(non_lighting_reject[:5])}"
        return BusinessJudgment(
            recommendation_level="D",
            decision="reject",
            project_type=project_type,
            business_direction="非照明主标的",
            doable_scope="",
            judgment_reason=reason,
            needs_vip_text=False,
            manual_review_reason="",
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=non_lighting_reject + excludes,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points,
            evidence=build_evidence(full_text, non_lighting_reject + scope + products + construction),
        )

    if not title_lighting and non_lighting_ambiguous and (scope or products or construction or generic_lighting):
        reason = (
            "标题/摘要/已读材料出现照明/路灯/灯具证据，但标题主标的是改造、养护、补短板、"
            "道路或农田水利等综合工程，照明可能只是附带项"
        )
        return BusinessJudgment(
            recommendation_level="C",
            decision="needs_review",
            project_type=project_type,
            business_direction="综合工程附带照明",
            doable_scope="需人工确认照明/路灯是否为独立可承接范围",
            judgment_reason=reason,
            needs_vip_text=not body_ok,
            manual_review_reason=f"主标的词: {', '.join(non_lighting_ambiguous[:5])}",
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=excludes,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points + ["照明疑似附带项，不能自动推荐"],
            evidence=build_evidence(full_text, non_lighting_ambiguous + construction + products + scope + generic_lighting),
        )

    if construction:
        business_direction = "工程施工/安装"
        doable_scope = ", ".join(construction[:5])
    elif products:
        business_direction = "户外灯具供货"
        doable_scope = ", ".join(products[:5])
    elif scope:
        business_direction = "照明/路灯/亮化相关"
        doable_scope = ", ".join(scope[:5])
    elif broad:
        business_direction = "改造提升类疑似机会"
        doable_scope = "需正文确认是否含照明/亮化/路灯/户外灯具"

    # 通用“灯具/节能灯具”不能直接代表我方户外照明业务。
    # 只有同时出现户外、道路、市政、公园、景观、亮化等语境，才进入推荐候选。
    if generic_lighting and not (scope or products or construction):
        if indoor_context and not title_lighting:
            manual_reason = f"疑似室内通用灯具场景: {', '.join(indoor_context[:5])}"
            return BusinessJudgment(
                recommendation_level="C",
                decision="needs_review",
                project_type=project_type,
                business_direction="室内通用灯具边界项目",
                doable_scope="需确认是否为我方可做户外灯具/照明业务",
                judgment_reason="只命中通用灯具词，且出现教室/办公室/室内等非户外语境，不能直接推荐",
                needs_vip_text=not body_ok,
                manual_review_reason=manual_reason,
                scope_hits=scope,
                product_hits=products,
                construction_hits=construction,
                broad_recall_hits=broad,
                exclude_hits=excludes,
                display_hits=display,
                maintenance_hits=maintenance,
                risk_points=risk_points + ["室内灯具语境优先级高于页面噪声中的户外词"],
                evidence=build_evidence(full_text, generic_lighting + indoor_context + outdoor_context),
            )
        if outdoor_context:
            scope = list(dict.fromkeys(scope + generic_lighting))
            business_direction = "户外/景观语境下的通用灯具"
            doable_scope = (
                f"{', '.join(generic_lighting[:3])}；"
                f"户外语境: {', '.join(outdoor_context[:3])}"
            )
        else:
            manual_reason = "通用灯具但未看到户外、路灯、亮化、景观等语境"
            if indoor_context:
                manual_reason = f"疑似室内通用灯具场景: {', '.join(indoor_context[:5])}"
            return BusinessJudgment(
                recommendation_level="C",
                decision="needs_review",
                project_type=project_type,
                business_direction="通用灯具边界项目",
                doable_scope="需确认是否为户外灯具/路灯/亮化灯具",
                judgment_reason="只命中通用灯具词，不能直接判定为可做户外照明业务",
                needs_vip_text=not body_ok,
                manual_review_reason=manual_reason,
                scope_hits=scope,
                product_hits=products,
                construction_hits=construction,
                broad_recall_hits=broad,
                exclude_hits=excludes,
                display_hits=display,
                maintenance_hits=maintenance,
                risk_points=risk_points,
                evidence=build_evidence(full_text, generic_lighting + indoor_context + outdoor_context),
            )

    # 维护类必须判断维护对象。
    if maintenance:
        # 先检查是否是学校/医院照明项目（标题含学校/医院+照明/灯具+更换/改造）
        school_hospital_words = ["学校", "医院", "卫生院", "教学楼", "校园"]
        lighting_maintenance_words = ["照明", "灯具", "路灯", "亮化"]
        is_school_hospital_lighting = (
            any(w in title for w in school_hospital_words) and
            any(w in title for w in lighting_maintenance_words)
        )
        if is_school_hospital_lighting:
            # 学校/医院照明更换/改造项目，标记为边界项目
            manual_reason = f"标题含学校/医院+照明/灯具词，疑似学校/医院照明边界项目，需确认是否为户外照明工程还是室内灯具更换"
            return BusinessJudgment(
                recommendation_level="C",
                decision="needs_review",
                project_type=project_type,
                business_direction="学校/医院照明维护/更换边界项目",
                doable_scope="需确认是否为户外路灯/亮化工程，还是室内灯具更换",
                judgment_reason=manual_reason,
                needs_vip_text=not body_ok,
                manual_review_reason=manual_reason,
                scope_hits=scope,
                product_hits=products,
                construction_hits=construction,
                broad_recall_hits=broad,
                exclude_hits=excludes,
                display_hits=display,
                maintenance_hits=maintenance,
                risk_points=risk_points + ["学校/医院照明维护/更换边界：需区分户外工程与室内小额更换"],
                evidence=build_evidence(full_text, school_hospital_words + lighting_maintenance_words + maintenance),
            )
        
        pv_maintenance_hits = hits(full_text, PV_MAINTENANCE_POSITIVE_WORDS)
        pv_evidence_hits = hits(full_text, PV_MAINTENANCE_EVIDENCE_WORDS)
        # 光伏维护判断：必须有明确光伏相关词，不能只有"更换""维护"等通用词
        has_pv_keyword = any(kw in full_text for kw in ["光伏", "太阳能", "分布式光伏"])
        if pv_maintenance_hits and pv_evidence_hits and has_pv_keyword:
            return BusinessJudgment(
                recommendation_level="C",
                decision="needs_review",
                project_type=project_type,
                business_direction="光伏维护/改造待复核",
                doable_scope="需确认我方是否承接光伏维护、组件清洗、电缆/PVC管/抗风绳拆装更换等现场施工范围",
                judgment_reason="光伏维护/更换类项目含施工工期、工程预算、承装承修承试资质或现场拆装证据，不能因电缆/配电词直接排除",
                needs_vip_text=False,
                manual_review_reason="光伏维护边界项目：确认是否为可承接现场施工，不是纯运维或纯物资",
                scope_hits=scope,
                product_hits=products,
                construction_hits=construction,
                broad_recall_hits=broad,
                exclude_hits=excludes,
                display_hits=display,
                maintenance_hits=maintenance,
                risk_points=risk_points + ["光伏维护/更换项目需业务复核"],
                evidence=build_evidence(full_text, pv_maintenance_hits + pv_evidence_hits + maintenance),
            )
        if scope or products:
            risk_points.append("维护/维修类项目，已命中照明或灯具对象，需要看是否为更换灯具/路灯/亮化设施")
        elif any(w in full_text for w in ["线路", "变压器", "配电", "电缆", "电房"]):
            return BusinessJudgment(
                recommendation_level="D",
                decision="reject",
                project_type=project_type,
                business_direction="非照明维护",
                doable_scope="",
                judgment_reason="维护对象偏线路/变压器/配电/电缆，不属于当前业务范围",
                needs_vip_text=False,
                manual_review_reason="",
                scope_hits=scope,
                product_hits=products,
                construction_hits=construction,
                broad_recall_hits=broad,
                exclude_hits=excludes,
                display_hits=display,
                maintenance_hits=maintenance,
                risk_points=risk_points,
                evidence=build_evidence(full_text, maintenance + ["线路", "变压器", "配电", "电缆", "电房"]),
            )
        else:
            risk_points.append("维护/维修类标题未明确维护对象")

    if scope or products or construction:
        if body_ok:
            level = "B" if risk_points else "A"
            reason = "正文/标题证据显示属于可做业务范围"
            if risk_points:
                reason = "属于可做业务范围，但存在主次或维护边界需业务确认"
            return BusinessJudgment(
                recommendation_level=level,
                decision="keep" if level in {"A", "B"} else "needs_review",
                project_type=project_type,
                business_direction=business_direction,
                doable_scope=doable_scope,
                judgment_reason=reason,
                needs_vip_text=False,
                manual_review_reason="; ".join(risk_points) if level == "B" else "",
                scope_hits=scope,
                product_hits=products,
                construction_hits=construction,
                broad_recall_hits=broad,
                exclude_hits=excludes,
                display_hits=display,
                maintenance_hits=maintenance,
                risk_points=risk_points,
                evidence=build_evidence(full_text, construction + products + scope + display + product_excludes),
            )
        return BusinessJudgment(
            recommendation_level="B",
            decision="provisional_keep",
            project_type=project_type,
            business_direction=business_direction,
            doable_scope=doable_scope,
            judgment_reason="标题/摘要命中可做业务，但正文未读取成功，需正文确认",
            needs_vip_text=True,
            manual_review_reason="正文缺失",
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=excludes,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points,
            evidence=build_evidence(full_text, construction + products + scope),
        )

    if broad:
        return BusinessJudgment(
            recommendation_level="C",
            decision="needs_review",
            project_type=project_type,
            business_direction=business_direction,
            doable_scope=doable_scope,
            judgment_reason="标题属于改造提升/市政景观类疑似机会，但未发现明确照明/亮化/路灯证据",
            needs_vip_text=not body_ok,
            manual_review_reason="需查正文清单或附件，确认是否包含建筑照明、亮化、路灯或户外灯具",
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=excludes,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points,
            evidence=build_evidence(full_text, broad),
        )

    # 标题含照明/路灯/亮化/光伏/充电桩但边界不清，不能直接排除，必须正文复判或待人工复核
    title_ambiguous_lighting = hits(title, AMBIGUOUS_TITLE_LIGHTING)
    if title_ambiguous_lighting:
        # 室内小额照明、学校/医院灯具更换：单独标注边界
        school_hospital_words = ["学校", "医院", "卫生院", "教学楼", "教学楼", "校园"]
        is_school_hospital = any(w in title for w in school_hospital_words)
        is_indoor_small = bool(indoor_context) and not any(w in title for w in ["路灯", "道路照明", "户外照明", "亮化工程", "景观亮化"])
        
        if is_school_hospital:
            manual_reason = f"标题含照明词({', '.join(title_ambiguous_lighting[:3])})且涉及学校/医院，疑似灯具更换/室内小额照明边界项目，需正文确认是否为户外照明工程"
            return BusinessJudgment(
                recommendation_level="C",
                decision="needs_review",
                project_type=project_type,
                business_direction="学校/医院照明边界项目",
                doable_scope="需确认是否为户外路灯/亮化工程，还是室内灯具更换",
                judgment_reason=manual_reason,
                needs_vip_text=not body_ok,
                manual_review_reason=manual_reason,
                scope_hits=scope,
                product_hits=products,
                construction_hits=construction,
                broad_recall_hits=broad,
                exclude_hits=excludes,
                display_hits=display,
                maintenance_hits=maintenance,
                risk_points=risk_points + ["学校/医院照明边界：需区分户外工程与室内小额更换"],
                evidence=build_evidence(full_text, title_ambiguous_lighting + school_hospital_words + scope + products),
            )
        if is_indoor_small:
            manual_reason = f"标题含照明词({', '.join(title_ambiguous_lighting[:3])})但疑似室内小额照明场景，需正文确认是否为户外照明工程"
            return BusinessJudgment(
                recommendation_level="C",
                decision="needs_review",
                project_type=project_type,
                business_direction="室内小额照明边界项目",
                doable_scope="需确认是否为户外路灯/亮化工程，还是室内小额灯具更换",
                judgment_reason=manual_reason,
                needs_vip_text=not body_ok,
                manual_review_reason=manual_reason,
                scope_hits=scope,
                product_hits=products,
                construction_hits=construction,
                broad_recall_hits=broad,
                exclude_hits=excludes,
                display_hits=display,
                maintenance_hits=maintenance,
                risk_points=risk_points + ["室内小额照明边界：需区分户外工程与室内小额更换"],
                evidence=build_evidence(full_text, title_ambiguous_lighting + indoor_context + scope + products),
            )
        # 通用边界：标题含照明词但正文证据不足
        manual_reason = f"标题含照明/路灯/亮化/光伏/充电桩词({', '.join(title_ambiguous_lighting[:3])})但正文证据不足，不能直接排除"
        return BusinessJudgment(
            recommendation_level="C",
            decision="needs_review",
            project_type=project_type,
            business_direction="照明边界项目待正文复判",
            doable_scope="需正文或附件确认是否为我方可做的户外照明/路灯/亮化/光伏施工业务",
            judgment_reason=manual_reason,
            needs_vip_text=not body_ok,
            manual_review_reason=manual_reason,
            scope_hits=scope,
            product_hits=products,
            construction_hits=construction,
            broad_recall_hits=broad,
            exclude_hits=excludes,
            display_hits=display,
            maintenance_hits=maintenance,
            risk_points=risk_points + ["标题含照明主业词但边界不清，需正文复判"],
            evidence=build_evidence(full_text, title_ambiguous_lighting + scope + products + construction),
        )

    return BusinessJudgment(
        recommendation_level="D",
        decision="reject",
        project_type=project_type,
        business_direction="无当前业务证据",
        doable_scope="",
        judgment_reason="未发现照明/路灯/亮化/户外灯具/分布式光伏施工等可做业务证据",
        needs_vip_text=False if body_ok else True,
        manual_review_reason="正文缺失时可抽样复核，但默认不推荐" if not body_ok else "",
        scope_hits=scope,
        product_hits=products,
        construction_hits=construction,
        broad_recall_hits=broad,
        exclude_hits=excludes,
        display_hits=display,
        maintenance_hits=maintenance,
        risk_points=risk_points,
        evidence=build_evidence(full_text, SERVICE_EXCLUDE + PRODUCT_EXCLUDE + DISPLAY_ONLY),
    )
