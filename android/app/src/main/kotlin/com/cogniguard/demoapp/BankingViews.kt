package com.cogniguard.demoapp

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.Button
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
    /** Android's bundled `org.json` returns the *literal string* `"null"` -- not the
     * fallback -- when a key's JSON value is an explicit JSON null (e.g. an
     * `Optional[str] = None` Pydantic field on the gateway), because `JSONObject.NULL`'s
     * `toString()` is `"null"` and `optString`'s internal stringify helper happily formats
     * that sentinel before ever consulting the fallback. Every nullable backend field must
     * go through this, not raw `optString`, to avoid that literal "null" leaking into the UI
     * (the root cause of the "Welcome back, null" dashboard bug found in prototype testing). */
    fun safeOptString(json: JSONObject, key: String, fallback: String = ""): String =
        if (json.isNull(key)) fallback else json.optString(key, fallback)

    /** Same fix as [safeOptString], but returns `null` (not `""`) for callers like
     * [formatInr]/[formatDateTime] that branch on absence rather than display "". */
    fun safeOptStringOrNull(json: JSONObject, key: String): String? =
        if (json.isNull(key)) null else json.optString(key)

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

    /** A rounded letter-avatar (reference parity: avatar-chip rows everywhere a list of
     * transactions/beneficiaries/devices/sessions is rendered). */
    private fun avatarCircle(context: Context, letter: String, bgRes: Int, sizeDp: Int = 36): TextView {
        val avatar = TextView(context)
        avatar.text = letter
        avatar.setBackgroundResource(bgRes)
        avatar.setTextColor(ContextCompat.getColor(context, R.color.white))
        avatar.textSize = 14f
        avatar.setTypeface(avatar.typeface, Typeface.BOLD)
        avatar.gravity = Gravity.CENTER
        avatar.layoutParams = LinearLayout.LayoutParams(dp(context, sizeDp), dp(context, sizeDp))
        return avatar
    }

    /** A rounded pill status badge (reference parity: light-tint background + colored
     * bold text, instead of a plain colored label). */
    private fun pillBadge(context: Context, text: String, isGood: Boolean): TextView {
        val pill = textView(context, text, 11f, if (isGood) R.color.success_green else R.color.cbi_neutral, bold = true)
        pill.setBackgroundResource(if (isGood) R.drawable.bg_pill_badge_success else R.drawable.bg_pill_badge_muted)
        pill.setPadding(dp(context, 10), dp(context, 4), dp(context, 10), dp(context, 4))
        return pill
    }

    private fun rowContainer(context: Context): LinearLayout {
        val row = LinearLayout(context)
        row.orientation = LinearLayout.HORIZONTAL
        row.gravity = Gravity.CENTER_VERTICAL
        val rowParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        rowParams.topMargin = dp(context, 4)
        rowParams.bottomMargin = dp(context, 4)
        row.layoutParams = rowParams
        return row
    }

    fun addTransactionRow(context: Context, container: LinearLayout, txn: JSONObject) {
        val row = rowContainer(context)

        val name = safeOptString(txn, "beneficiary_name").ifBlank { safeOptString(txn, "masked_beneficiary_account", "--") }
        val avatarParams = LinearLayout.LayoutParams(dp(context, 36), dp(context, 36))
        avatarParams.marginEnd = dp(context, 12)
        val avatar = avatarCircle(context, name.take(1).uppercase(), R.drawable.bg_badge_circle_primary)
        avatar.layoutParams = avatarParams

        val textColumn = LinearLayout(context)
        textColumn.orientation = LinearLayout.VERTICAL
        textColumn.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        textColumn.addView(textView(context, name, 14f, R.color.cbi_text, bold = true))
        val sub =
            textView(
                context,
                "${safeOptString(txn, "transfer_type", "--")} · ${safeOptString(txn, "status", "--")} · ${formatDateTime(safeOptStringOrNull(txn, "initiated_at"))}",
                12f,
                R.color.cbi_text_muted,
            )
        val subParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        subParams.topMargin = dp(context, 2)
        sub.layoutParams = subParams
        textColumn.addView(sub)

        val amount = textView(context, formatInr(txn.optDouble("amount").takeIf { !it.isNaN() }, safeOptStringOrNull(txn, "currency")), 15f, R.color.cbi_text, bold = true)
        val amountParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        amountParams.marginStart = dp(context, 8)
        amount.layoutParams = amountParams

        row.addView(avatar)
        row.addView(textColumn)
        row.addView(amount)
        container.addView(row)
    }

    fun addBeneficiaryRow(context: Context, container: LinearLayout, beneficiary: JSONObject) {
        val row = rowContainer(context)

        val verified = beneficiary.optBoolean("is_verified")
        val name = safeOptString(beneficiary, "name", "--")
        val avatarParams = LinearLayout.LayoutParams(dp(context, 36), dp(context, 36))
        avatarParams.marginEnd = dp(context, 12)
        val avatar = avatarCircle(context, name.take(1).uppercase(), if (verified) R.drawable.bg_badge_circle_success else R.drawable.bg_badge_circle_neutral)
        avatar.layoutParams = avatarParams

        val textColumn = LinearLayout(context)
        textColumn.orientation = LinearLayout.VERTICAL
        textColumn.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        textColumn.addView(textView(context, name, 14f, R.color.cbi_text, bold = true))
        textColumn.addView(textView(context, safeOptString(beneficiary, "masked_account_number", "--"), 12f, R.color.cbi_text_muted))

        val status = pillBadge(context, if (verified) "Verified" else "Unverified", verified)
        val statusParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        statusParams.marginStart = dp(context, 8)
        status.layoutParams = statusParams

        row.addView(avatar)
        row.addView(textColumn)
        row.addView(status)
        container.addView(row)
    }

    /** A single qualitative status line for [SecurityCenterActivity] -- an icon chip +
     * label + pill status badge. Deliberately takes no numeric score: callers pass an
     * already customer-facing phrase ("Trusted" / "Verified" / "Calibrating"), never a
     * raw model score (CLAUDE.md: no model names/raw scores on the customer surface). */
    fun addStatusRow(context: Context, container: LinearLayout, label: String, status: String, isGood: Boolean) {
        val row = rowContainer(context)

        val iconParams = LinearLayout.LayoutParams(dp(context, 32), dp(context, 32))
        iconParams.marginEnd = dp(context, 12)
        val icon = avatarCircle(context, if (isGood) "✓" else "…", if (isGood) R.drawable.bg_badge_circle_success else R.drawable.bg_badge_circle_neutral, sizeDp = 32)
        icon.layoutParams = iconParams

        val labelView = textView(context, label, 14f, R.color.cbi_text)
        labelView.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)

        val statusView = pillBadge(context, status, isGood)
        val statusParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        statusParams.marginStart = dp(context, 8)
        statusView.layoutParams = statusParams

        row.addView(icon)
        row.addView(labelView)
        row.addView(statusView)
        container.addView(row)
    }

    /** Device row with optional Trust button.
     * [onTrust] receives the device_id; pass null for read-only display. */
    fun addDeviceRow(
        context: Context,
        container: LinearLayout,
        device: JSONObject,
        onTrust: ((deviceId: String) -> Unit)? = null,
    ) {
        val outerCol = LinearLayout(context)
        outerCol.orientation = LinearLayout.VERTICAL
        outerCol.layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)

        val row = rowContainer(context)
        val trusted = device.optBoolean("is_trusted")
        val deviceId = safeOptString(device, "device_id", "")
        val label = safeOptString(device, "label").ifBlank { deviceId.take(8).ifBlank { "--" } }

        val avatarParams = LinearLayout.LayoutParams(dp(context, 36), dp(context, 36))
        avatarParams.marginEnd = dp(context, 12)
        val avatar = avatarCircle(context, label.take(1).uppercase(), if (trusted) R.drawable.bg_badge_circle_success else R.drawable.bg_badge_circle_neutral)
        avatar.layoutParams = avatarParams

        val labelView = textView(context, label, 14f, R.color.cbi_text)
        labelView.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)

        val status = pillBadge(context, if (trusted) "Trusted" else "Not trusted", trusted)
        val statusParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        statusParams.marginStart = dp(context, 8)
        status.layoutParams = statusParams

        row.addView(avatar)
        row.addView(labelView)
        row.addView(status)
        outerCol.addView(row)

        if (onTrust != null && !trusted && deviceId.isNotEmpty()) {
            val btn = actionButton(context, "Trust this device")
            btn.setOnClickListener {
                btn.isEnabled = false
                btn.text = "Trusting…"
                onTrust(deviceId)
            }
            outerCol.addView(btn)
        }

        container.addView(outerCol)
    }

    /** Session row with optional Revoke button.
     * [onRevoke] receives the session_id; pass null for read-only display. */
    fun addSessionRow(
        context: Context,
        container: LinearLayout,
        session: JSONObject,
        onRevoke: ((sessionId: String) -> Unit)? = null,
    ) {
        val outerCol = LinearLayout(context)
        outerCol.orientation = LinearLayout.VERTICAL
        outerCol.layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)

        val row = rowContainer(context)
        val sessionId = safeOptString(session, "session_id", "")
        val label = safeOptString(session, "device_label").ifBlank { sessionId.take(8).ifBlank { "--" } }

        val avatarParams = LinearLayout.LayoutParams(dp(context, 36), dp(context, 36))
        avatarParams.marginEnd = dp(context, 12)
        val avatar = avatarCircle(context, label.take(1).uppercase(), R.drawable.bg_badge_circle_primary)
        avatar.layoutParams = avatarParams

        val textCol = LinearLayout(context)
        textCol.orientation = LinearLayout.VERTICAL
        textCol.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        textCol.addView(textView(context, label, 14f, R.color.cbi_text))
        val loc = safeOptString(session, "location").ifBlank { "--" }
        textCol.addView(textView(context, loc, 12f, R.color.cbi_text_muted))

        row.addView(avatar)
        row.addView(textCol)
        outerCol.addView(row)

        if (onRevoke != null && sessionId.isNotEmpty()) {
            val btn = actionButton(context, "Revoke session", isDestructive = true)
            btn.setOnClickListener {
                btn.isEnabled = false
                btn.text = "Revoking…"
                onRevoke(sessionId)
            }
            outerCol.addView(btn)
        }

        container.addView(outerCol)
    }

    private fun actionButton(context: Context, label: String, isDestructive: Boolean = false): Button {
        val btn = Button(context)
        btn.text = label
        btn.textSize = 12f
        btn.setTextColor(if (isDestructive) Color.parseColor("#DC2626") else ContextCompat.getColor(context, R.color.cbi_primary))
        btn.setBackgroundResource(R.drawable.bg_pill_badge_muted)
        val params = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, dp(context, 32))
        params.topMargin = dp(context, 6)
        params.marginStart = dp(context, 48)  // align under label, past avatar
        btn.layoutParams = params
        btn.setPadding(dp(context, 16), 0, dp(context, 16), 0)
        return btn
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
