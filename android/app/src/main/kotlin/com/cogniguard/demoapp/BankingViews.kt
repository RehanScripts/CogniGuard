package com.cogniguard.demoapp

import android.content.Context
import android.graphics.Typeface
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Small, dependency-free view builders shared by [DashboardActivity], [SecurityCenterActivity],
 * and [TransactionHistoryActivity] -- rows are built programmatically (no RecyclerView/adapter
 * boilerplate) since every list here is short (a handful of accounts/transactions/beneficiaries),
 * mirroring how `web-app/src/pages/Transactions.tsx` simply `.map()`s the same `/api/v1/banking`
 * responses straight into list rows.
 */
object BankingViews {
    fun dp(context: Context, value: Int): Int =
        TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value.toFloat(), context.resources.displayMetrics).toInt()

    fun formatInr(amount: Double?, currency: String?): String {
        if (amount == null) return "--"
        val symbol = if (currency == null || currency == "INR") "₹" else "$currency "
        return symbol + String.format(Locale.US, "%,.2f", amount)
    }

    /** `2026-06-23T10:15:00Z` -> `23 Jun, 10:15 am`; falls back to the raw string for any
     * value that isn't a parseable ISO instant (never crashes a demo screen on bad data). */
    fun formatDateTime(iso: String?): String {
        if (iso.isNullOrBlank()) return "--"
        return try {
            val instant = Instant.parse(iso)
            val fmt = DateTimeFormatter.ofPattern("d MMM, h:mm a", Locale.US).withZone(ZoneId.systemDefault())
            fmt.format(instant)
        } catch (e: Exception) {
            iso
        }
    }

    fun formatDate(iso: String?): String {
        if (iso.isNullOrBlank()) return "--"
        return try {
            val instant = Instant.parse(iso)
            val fmt = DateTimeFormatter.ofPattern("d MMM yyyy", Locale.US).withZone(ZoneId.systemDefault())
            fmt.format(instant)
        } catch (e: Exception) {
            iso
        }
    }

    fun addDivider(context: Context, container: LinearLayout) {
        val divider = View(context)
        divider.setBackgroundColor(ContextCompat.getColor(context, R.color.cbi_divider))
        val params = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(context, 1))
        params.topMargin = dp(context, 10)
        params.bottomMargin = dp(context, 10)
        divider.layoutParams = params
        container.addView(divider)
    }

    private fun textView(
        context: Context,
        text: String,
        sizeSp: Float,
        colorRes: Int,
        bold: Boolean = false,
    ): TextView {
        val tv = TextView(context)
        tv.text = text
        tv.textSize = sizeSp
        tv.setTextColor(ContextCompat.getColor(context, colorRes))
        if (bold) tv.setTypeface(tv.typeface, Typeface.BOLD)
        return tv
    }

    fun addTransactionRow(context: Context, container: LinearLayout, txn: JSONObject) {
        val row = LinearLayout(context)
        row.orientation = LinearLayout.VERTICAL

        val top = LinearLayout(context)
        top.orientation = LinearLayout.HORIZONTAL
        val name =
            textView(
                context,
                txn.optString("beneficiary_name").ifBlank { txn.optString("masked_beneficiary_account", "--") },
                15f,
                R.color.cbi_text,
            )
        name.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        val amount = textView(context, formatInr(txn.optDouble("amount").takeIf { !it.isNaN() }, txn.optString("currency", null)), 15f, R.color.cbi_text, bold = true)
        top.addView(name)
        top.addView(amount)

        val sub =
            textView(
                context,
                "${txn.optString("transfer_type", "--")} · ${txn.optString("status", "--")} · ${formatDateTime(txn.optString("initiated_at", null))}",
                12f,
                R.color.cbi_text_muted,
            )
        val subParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        subParams.topMargin = dp(context, 2)
        sub.layoutParams = subParams

        row.addView(top)
        row.addView(sub)
        container.addView(row)
    }

    fun addBeneficiaryRow(context: Context, container: LinearLayout, beneficiary: JSONObject) {
        val row = LinearLayout(context)
        row.orientation = LinearLayout.HORIZONTAL
        row.gravity = Gravity.CENTER_VERTICAL

        val label =
            textView(
                context,
                "${beneficiary.optString("name", "--")} (${beneficiary.optString("masked_account_number", "--")})",
                14f,
                R.color.cbi_text,
            )
        label.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)

        val verified = beneficiary.optBoolean("is_verified")
        val status = textView(context, if (verified) "Verified" else "Unverified", 12f, if (verified) R.color.success_green else R.color.cbi_text_muted)

        row.addView(label)
        row.addView(status)
        container.addView(row)
    }

    /** A single qualitative status line for [SecurityCenterActivity] -- a colored dot +
     * label + status text. Deliberately takes no numeric score: callers pass an already
     * customer-facing phrase ("Trusted" / "Verified" / "Calibrating"), never a raw
     * model score (CLAUDE.md: no model names/raw scores on the customer surface). */
    fun addStatusRow(context: Context, container: LinearLayout, label: String, status: String, isGood: Boolean) {
        val row = LinearLayout(context)
        row.orientation = LinearLayout.HORIZONTAL
        row.gravity = Gravity.CENTER_VERTICAL
        val rowParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        rowParams.topMargin = dp(context, 4)
        rowParams.bottomMargin = dp(context, 4)
        row.layoutParams = rowParams

        val dot = View(context)
        dot.setBackgroundResource(if (isGood) R.drawable.bg_status_dot_success else R.drawable.bg_status_dot_muted)
        val dotParams = LinearLayout.LayoutParams(dp(context, 10), dp(context, 10))
        dotParams.marginEnd = dp(context, 10)
        dot.layoutParams = dotParams

        val labelView = textView(context, label, 14f, R.color.cbi_text)
        labelView.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)

        val statusView = textView(context, status, 13f, if (isGood) R.color.success_green else R.color.cbi_text_muted, bold = true)

        row.addView(dot)
        row.addView(labelView)
        row.addView(statusView)
        container.addView(row)
    }

    fun addDeviceRow(context: Context, container: LinearLayout, device: JSONObject) {
        val row = LinearLayout(context)
        row.orientation = LinearLayout.HORIZONTAL
        row.gravity = Gravity.CENTER_VERTICAL

        val label = textView(context, device.optString("label").ifBlank { device.optString("device_id", "--") }, 14f, R.color.cbi_text)
        label.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)

        val trusted = device.optBoolean("is_trusted")
        val status = textView(context, if (trusted) "Trusted" else "Not trusted", 12f, if (trusted) R.color.success_green else R.color.cbi_text_muted)

        row.addView(label)
        row.addView(status)
        container.addView(row)
    }

    fun addSessionRow(context: Context, container: LinearLayout, session: JSONObject) {
        val row = LinearLayout(context)
        row.orientation = LinearLayout.HORIZONTAL
        row.gravity = Gravity.CENTER_VERTICAL

        val label = textView(context, session.optString("device_label").ifBlank { session.optString("session_id", "--") }, 14f, R.color.cbi_text)
        label.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)

        val location = textView(context, session.optString("location").ifBlank { "--" }, 12f, R.color.cbi_text_muted)

        row.addView(label)
        row.addView(location)
        container.addView(row)
    }

    /** A quick-action tile (colored letter badge + label) for the Dashboard's action row. */
    fun addQuickAction(
        context: Context,
        container: LinearLayout,
        letter: String,
        badgeBg: Int,
        label: String,
        onClick: () -> Unit,
    ) {
        val tile = LinearLayout(context)
        tile.orientation = LinearLayout.VERTICAL
        tile.gravity = Gravity.CENTER_HORIZONTAL
        tile.isClickable = true
        tile.isFocusable = true
        val tileParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        tile.layoutParams = tileParams
        tile.setOnClickListener { onClick() }

        val badge = TextView(context)
        badge.text = letter
        badge.setBackgroundResource(badgeBg)
        badge.setTextColor(ContextCompat.getColor(context, R.color.white))
        badge.textSize = 16f
        badge.setTypeface(badge.typeface, Typeface.BOLD)
        badge.gravity = Gravity.CENTER
        badge.layoutParams = LinearLayout.LayoutParams(dp(context, 48), dp(context, 48))

        val labelView = textView(context, label, 12f, R.color.cbi_text)
        labelView.gravity = Gravity.CENTER_HORIZONTAL
        val labelParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        labelParams.topMargin = dp(context, 6)
        labelView.layoutParams = labelParams

        tile.addView(badge)
        tile.addView(labelView)
        container.addView(tile)
    }
}
