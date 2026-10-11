resource "time_static" "budget_start" {}

# Amount 100 with 50 % and 100 % thresholds: alerts at USD 50 and USD 100 of the USD 200 trial credit.
resource "azurerm_consumption_budget_subscription" "main" {
  name            = "${var.prefix}-budget"
  subscription_id = data.azurerm_subscription.current.id
  amount          = 100
  time_grain      = "Monthly"

  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", time_static.budget_start.rfc3339)
  }

  notification {
    enabled        = true
    operator       = "GreaterThanOrEqualTo"
    threshold      = 50
    threshold_type = "Actual"
    contact_emails = var.budget_alert_emails
  }

  notification {
    enabled        = true
    operator       = "GreaterThanOrEqualTo"
    threshold      = 100
    threshold_type = "Actual"
    contact_emails = var.budget_alert_emails
  }

  lifecycle {
    ignore_changes = [time_period]
  }
}
