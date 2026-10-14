from app.config import settings
from app.core.fill_engine import FillConfig


def fill_config() -> FillConfig:
    return FillConfig(
        stock_slippage_bps=settings.stock_slippage_bps,
        option_slippage_pct=settings.option_slippage_pct,
        stock_commission_per_share=settings.stock_commission_per_share,
        option_commission_per_contract=settings.option_commission_per_contract,
    )


def downsample(points: list, max_points: int = 5000) -> list:
    if len(points) <= max_points:
        return points
    step = -(-len(points) // max_points)
    out = points[::step]
    if out[-1] is not points[-1]:
        out.append(points[-1])
    return out
