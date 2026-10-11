TOOL_GET_PRODUCT = "get_product"                   # (product_id: str) -> Product
TOOL_LIST_PRODUCTS = "list_products"               # (category: ProductCategory | None) -> list[Product]
TOOL_COMPARE_PRODUCTS = "compare_products"         # (product_ids: list[str], 2..3) -> list[Product]
TOOL_GET_CUSTOMER_PROFILE = "get_customer_profile" # (customer_id: str) -> CustomerProfile
TOOL_GET_CUSTOMER_FIELDS = "get_customer_fields"   # (customer_id: str, fields: list[Level2Field]) -> CustomerFields | FieldsDenied
