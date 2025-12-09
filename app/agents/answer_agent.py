# app/agents/answer_agent.py
from typing import List, Dict, Any

SYSTEM = """
You are a helpful grocery shopping assistant. Summarize the cheapest prices and
highlight any deals succinctly. Prefer short bullets with store, price, and
savings. If multiple stores tie, list them. Offer one sensible next step.
"""

class AnswerAgent:
    def craft_best_price(self, user_message: str, rows: List[Dict[str, Any]]) -> str:
        # rows is a list of dicts shaped like BestPriceRow:
        #   { product_name, brand?, category?, offers: [{store, price, is_deal, deal_type, list_price, ...}, ...] }
        if not rows:
            return ("I couldn’t find priced offers for that yet. Try a simpler phrase like "
                    "“milk” or add a size (e.g., “whole milk 1 gal”).")

        # Flatten offers with product context
        flat: List[Dict[str, Any]] = []
        for r in rows:
            offers = r.get("offers") or []
            for o in offers:
                if o.get("price") is None:
                    continue
                flat.append({
                    "product_name": r.get("product_name"),
                    "category": r.get("category"),
                    "store": o.get("store"),
                    "price": o.get("price"),
                    "list_price": o.get("list_price"),
                    "is_deal": o.get("is_deal"),
                    "deal_type": o.get("deal_type"),
                    "discount_pct": o.get("discount_pct"),
                    "discount_abs": o.get("discount_abs"),
                })

        if not flat:
            return ("I found matching products, but no prices were available. "
                    "Try broadening the query or removing the price cap.")

        # Sort by price asc, then by highest discount_pct
        flat.sort(key=lambda x: (x["price"], -(x.get("discount_pct") or 0)))

        # Build concise summary
        lines: List[str] = ["Here are the best prices I found:"]
        best_overall = flat[0]

        # Top 3 bullets
        for item in flat[:3]:
            parts = [f"• {item['product_name']} — {item['store']} ${item['price']:.2f}"]
            if item.get("list_price"):
                parts.append(f"(was ${item['list_price']:.2f})")
            if item.get("is_deal"):
                label = item.get("deal_type") or "DEAL"
                parts.append(f"[{label}]")
            if item.get("discount_pct"):
                parts.append(f"save {int(round(item['discount_pct'] * 100))}%")
            lines.append(" ".join(parts))

        # Simple next step
        lines.append("")
        lines.append(f"Best overall: {best_overall['product_name']} at {best_overall['store']} "
                     f"for ${best_overall['price']:.2f}.")
        lines.append("Tip: add a size/brand to narrow it down (e.g., “whole milk 1 gal”).")

        return "\n".join(lines)
