from app.core.db.models.models import PlanEnum


def get_channel_limit(plan: PlanEnum, extended_free: bool) -> int:
    if plan == PlanEnum.base or plan == PlanEnum.pro:
        return 999
    if extended_free:
        return 3
    return 1


def get_daily_post_limit(plan: PlanEnum, extended_free: bool) -> int:
    if plan == PlanEnum.pro:
        return 999
    if plan == PlanEnum.base:
        return 50
    if extended_free:
        return 5
    return 3


def get_daily_generation_limit(plan: PlanEnum, extended_free: bool) -> int:
    if plan == PlanEnum.pro:
        return 999
    if plan == PlanEnum.base:
        return 100
    if extended_free:
        return 10
    return 5
