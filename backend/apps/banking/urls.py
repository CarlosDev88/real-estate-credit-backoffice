from django.urls import path

from apps.banking import views

app_name = "banking"

urlpatterns = [
    # Bancos y productos (sección 23.2)
    path("banks", views.BankListView.as_view(), name="bank-list"),
    path("banks/<uuid:bank_id>", views.BankDetailView.as_view(), name="bank-detail"),
    path("banks/<uuid:bank_id>/activate", views.BankActivateView.as_view(), name="bank-activate"),
    path(
        "banks/<uuid:bank_id>/deactivate",
        views.BankDeactivateView.as_view(),
        name="bank-deactivate",
    ),
    path("bank-products", views.BankProductListView.as_view(), name="bank-product-list"),
    path(
        "bank-products/<uuid:product_id>",
        views.BankProductDetailView.as_view(),
        name="bank-product-detail",
    ),
    path(
        "bank-products/<uuid:product_id>/activate",
        views.BankProductActivateView.as_view(),
        name="bank-product-activate",
    ),
    path(
        "bank-products/<uuid:product_id>/deactivate",
        views.BankProductDeactivateView.as_view(),
        name="bank-product-deactivate",
    ),
    path(
        "bank-products/<uuid:product_id>/purposes",
        views.BankProductPurposesView.as_view(),
        name="bank-product-purposes",
    ),
    # Reglas operativas (sección 23.3)
    path("bank-policy-rules", views.BankPolicyRuleListView.as_view(), name="bank-policy-rule-list"),
    path(
        "bank-policy-rules/<uuid:rule_id>",
        views.BankPolicyRuleDetailView.as_view(),
        name="bank-policy-rule-detail",
    ),
    path(
        "bank-policy-rules/<uuid:rule_id>/activate",
        views.BankPolicyRuleActivateView.as_view(),
        name="bank-policy-rule-activate",
    ),
    path(
        "bank-policy-rules/<uuid:rule_id>/deactivate",
        views.BankPolicyRuleDeactivateView.as_view(),
        name="bank-policy-rule-deactivate",
    ),
    path(
        "bank-policy-rules/<uuid:rule_id>/test",
        views.BankPolicyRuleTestView.as_view(),
        name="bank-policy-rule-test",
    ),
    path(
        "bank-policy-rules/<uuid:rule_id>/versions",
        views.BankPolicyRuleVersionsView.as_view(),
        name="bank-policy-rule-versions",
    ),
]
