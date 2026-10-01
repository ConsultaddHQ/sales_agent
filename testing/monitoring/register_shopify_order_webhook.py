#!/usr/bin/env python3
"""Register the Shopify ORDERS_CREATE webhook pointing at our onboarding service.

Dry-run by default; pass --apply to create the subscription. Lists existing
subscriptions first and skips if one already targets the callback URL.

Env: SHOPIFY_SHOP (e.g. goxfused.myshopify.com), SHOPIFY_ADMIN_TOKEN (needs read_orders;
     webhook subscriptions need no extra scope for orders topics).
Note: Shopify signs deliveries with the custom app's client secret -> that value
      is SHOPIFY_WEBHOOK_SECRET on the server.
"""
import argparse
import os
import sys

import requests

API_VERSION = "2026-07"
CALLBACK_URL = "https://api.teampop.com/webhooks/shopify/orders-create"

LIST_QUERY = """
query { webhookSubscriptions(first: 100, topics: [ORDERS_CREATE]) {
  nodes { id topic endpoint { __typename ... on WebhookHttpEndpoint { callbackUrl } } } } }
"""
CREATE_MUTATION = """
mutation($url: URL!) { webhookSubscriptionCreate(topic: ORDERS_CREATE,
  webhookSubscription: {callbackUrl: $url, format: JSON}) {
  webhookSubscription { id } userErrors { field message } } }
"""


def gql(shop: str, token: str, query: str, variables=None) -> dict:
    r = requests.post(
        f"https://{shop}/admin/api/{API_VERSION}/graphql.json",
        json={"query": query, "variables": variables or {}},
        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body["data"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="actually create the subscription")
    args = ap.parse_args()

    shop, token = os.getenv("SHOPIFY_SHOP"), os.getenv("SHOPIFY_ADMIN_TOKEN")
    if not shop or not token:
        print("Set SHOPIFY_SHOP and SHOPIFY_ADMIN_TOKEN", file=sys.stderr)
        return 2

    nodes = gql(shop, token, LIST_QUERY)["webhookSubscriptions"]["nodes"]
    for n in nodes:
        if (n.get("endpoint") or {}).get("callbackUrl") == CALLBACK_URL:
            print(f"Already registered ({n['id']}) -> {CALLBACK_URL}; nothing to do.")
            return 0
    print(f"{len(nodes)} existing ORDERS_CREATE subscription(s), none for {CALLBACK_URL}.")
    if not args.apply:
        print(f"[dry-run] would create ORDERS_CREATE -> {CALLBACK_URL} on {shop} (use --apply)")
        return 0

    res = gql(shop, token, CREATE_MUTATION, {"url": CALLBACK_URL})["webhookSubscriptionCreate"]
    if res["userErrors"]:
        print(f"Failed: {res['userErrors']}", file=sys.stderr)
        return 1
    print(f"Created {res['webhookSubscription']['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
