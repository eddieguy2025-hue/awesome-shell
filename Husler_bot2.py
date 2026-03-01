"""
Husler_bot2 - Content & Visual Automation Bot

Responsible for:
- Automating generation of ad content and visual requirements
- Posting ads that direct potential customers to the correct payment page
- Triggering follow-up actions when a new purchase is activated
"""

import json
import logging
import os
import random
import string
import textwrap
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Husler_bot2] %(levelname)s: %(message)s",
)
logger = logging.getLogger("Husler_bot2")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AdContent:
    """Holds all generated content for a single ad."""

    campaign_id: str
    product: str
    headline: str
    body_copy: str
    cta: str                         # call-to-action text
    payment_url: str
    image_spec: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class PurchaseEvent:
    """Represents a completed purchase that triggers follow-up actions."""

    purchase_id: str
    product: str
    customer_email: str
    amount: float
    currency: str = "USD"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# Content templates
# ---------------------------------------------------------------------------

_HEADLINE_TEMPLATES = [
    "Discover {product} – Limited Time Offer!",
    "Get {product} Today and Save Big!",
    "Transform Your Experience with {product}",
    "Don't Miss Out on {product} – Shop Now!",
    "{product}: The Smart Choice for You",
]

_BODY_TEMPLATES = [
    (
        "Looking for the best {product}? Look no further. "
        "Our top-rated offering delivers quality and value you can trust. "
        "Click below to secure yours before stock runs out."
    ),
    (
        "{product} is now available at an unbeatable price. "
        "Join thousands of satisfied customers who have already made the switch. "
        "Order today and enjoy fast, reliable delivery."
    ),
    (
        "Elevate your lifestyle with {product}. "
        "Expertly crafted and backed by our satisfaction guarantee, "
        "this is the upgrade you've been waiting for."
    ),
]

_CTA_OPTIONS = [
    "Buy Now",
    "Get Yours Today",
    "Shop Now",
    "Claim Your Deal",
    "Order Now",
]

_IMAGE_DIMENSIONS = [
    {"width": 1200, "height": 628, "format": "JPEG", "platform": "Facebook/OG"},
    {"width": 1080, "height": 1080, "format": "JPEG", "platform": "Instagram Square"},
    {"width": 1080, "height": 1920, "format": "JPEG", "platform": "Instagram Story"},
    {"width": 300,  "height": 250,  "format": "PNG",  "platform": "Display Ad"},
]


# ---------------------------------------------------------------------------
# HuslerBot2
# ---------------------------------------------------------------------------

class HuslerBot2:
    """Content & visual automation bot."""

    def __init__(
        self,
        payment_base_url: str = "http://localhost:8080/payment",
        output_dir: str = "husler_output",
    ):
        self._payment_base_url = payment_base_url.rstrip("/")
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._ads: list[AdContent] = []
        self._purchases: list[PurchaseEvent] = []

    # ------------------------------------------------------------------
    # Content generation
    # ------------------------------------------------------------------

    def generate_ad(
        self,
        campaign_id: str,
        product: str,
        extra_context: Optional[dict] = None,
    ) -> AdContent:
        """Generate ad content and image specs for a campaign."""
        ctx = {"product": product, **(extra_context or {})}

        headline = random.choice(_HEADLINE_TEMPLATES).format(**ctx)
        body_copy = random.choice(_BODY_TEMPLATES).format(**ctx)
        cta = random.choice(_CTA_OPTIONS)
        payment_url = self._build_payment_url(campaign_id, product)
        image_spec = self._build_image_spec(product)

        ad = AdContent(
            campaign_id=campaign_id,
            product=product,
            headline=headline,
            body_copy=body_copy,
            cta=cta,
            payment_url=payment_url,
            image_spec=image_spec,
        )
        self._ads.append(ad)
        logger.info("Generated ad for campaign %s / product '%s'", campaign_id, product)
        return ad

    def _build_payment_url(self, campaign_id: str, product: str) -> str:
        """Return a payment URL that includes properly encoded tracking parameters."""
        params = urllib.parse.urlencode({"campaign": campaign_id, "product": product})
        return f"{self._payment_base_url}?{params}"

    def _build_image_spec(self, product: str) -> dict:
        """Return visual requirements for all ad sizes."""
        return {
            "product": product,
            "background_color": "#2c3e50",
            "text_color": "#ffffff",
            "accent_color": "#e74c3c",
            "sizes": _IMAGE_DIMENSIONS,
            "notes": (
                "Use high-contrast imagery. Include product name in all sizes. "
                "CTA button should use accent color."
            ),
        }

    # ------------------------------------------------------------------
    # Ad posting (simulation layer)
    # ------------------------------------------------------------------

    def post_ad(self, ad: AdContent, channels: Optional[list] = None) -> dict:
        """Simulate posting an ad to one or more channels.

        In a production environment this method would integrate with
        platform-specific ad APIs (Facebook Ads, Google Ads, etc.).
        """
        channels = channels or ["facebook", "instagram", "display"]
        results: dict[str, dict] = {}
        for channel in channels:
            post_id = self._random_id()
            results[channel] = {
                "status": "posted",
                "post_id": post_id,
                "payment_url": ad.payment_url,
            }
            logger.info(
                "Ad %s posted to %s (post_id=%s, url=%s)",
                ad.campaign_id,
                channel,
                post_id,
                ad.payment_url,
            )
        return results

    # ------------------------------------------------------------------
    # Purchase activation handling
    # ------------------------------------------------------------------

    def on_purchase_activated(self, event: PurchaseEvent) -> None:
        """Handle actions triggered when a new purchase is activated."""
        self._purchases.append(event)
        logger.info(
            "Purchase activated: %s  product=%s  amount=%.2f %s  customer=%s",
            event.purchase_id,
            event.product,
            event.amount,
            event.currency,
            event.customer_email,
        )
        self._send_confirmation(event)
        self._update_inventory(event)

    def _send_confirmation(self, event: PurchaseEvent) -> None:
        """Simulate sending a purchase-confirmation message to the customer."""
        logger.info(
            "Confirmation queued for %s (purchase %s)",
            event.customer_email,
            event.purchase_id,
        )

    def _update_inventory(self, event: PurchaseEvent) -> None:
        """Simulate updating inventory after a purchase."""
        logger.info("Inventory updated for product '%s'", event.product)

    # ------------------------------------------------------------------
    # Campaign orchestration
    # ------------------------------------------------------------------

    def run_campaign(self, config: dict) -> dict:
        """Run a complete campaign: generate ads, post them, return results.

        *config* keys:
        - campaign_id  (str)  – unique campaign identifier
        - product      (str)  – product name / description
        - channels     (list) – optional list of posting channels
        """
        campaign_id = config.get("campaign_id", self._random_id())
        product = config.get("product", "Product")
        channels = config.get("channels")

        ad = self.generate_ad(campaign_id, product)
        post_results = self.post_ad(ad, channels)

        report = {
            "campaign_id": campaign_id,
            "ad": {
                "headline": ad.headline,
                "body_copy": ad.body_copy,
                "cta": ad.cta,
                "payment_url": ad.payment_url,
            },
            "image_spec": ad.image_spec,
            "post_results": post_results,
        }

        self._save_report(campaign_id, report)
        return report

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_report(self, campaign_id: str, report: dict) -> None:
        """Write the campaign report to a JSON file in *output_dir*."""
        filename = self._output_dir / f"{campaign_id}-report.json"
        with open(filename, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        logger.info("Campaign report saved: %s", filename)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _random_id(length: int = 8) -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Husler_bot2 – ad automation bot")
    parser.add_argument("--campaign-id", default=None, help="Campaign identifier")
    parser.add_argument("--product", required=True, help="Product name")
    parser.add_argument(
        "--channels",
        nargs="*",
        default=None,
        help="Channels to post to (e.g. facebook instagram display)",
    )
    parser.add_argument(
        "--payment-url",
        default="http://localhost:8080/payment",
        help="Base URL of the payment page",
    )
    parser.add_argument(
        "--output-dir",
        default="husler_output",
        help="Directory for campaign reports",
    )
    # Simulate a purchase activation
    parser.add_argument(
        "--simulate-purchase",
        action="store_true",
        help="Fire a simulated purchase-activated event after the campaign",
    )
    args = parser.parse_args()

    bot = HuslerBot2(
        payment_base_url=args.payment_url,
        output_dir=args.output_dir,
    )

    campaign_config = {
        "product": args.product,
        "channels": args.channels,
    }
    if args.campaign_id:
        campaign_config["campaign_id"] = args.campaign_id

    report = bot.run_campaign(campaign_config)
    print(json.dumps(report, indent=2))

    if args.simulate_purchase:
        purchase = PurchaseEvent(
            purchase_id=HuslerBot2._random_id(),
            product=args.product,
            customer_email="customer@example.com",
            amount=29.99,
        )
        bot.on_purchase_activated(purchase)
