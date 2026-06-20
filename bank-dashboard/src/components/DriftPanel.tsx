// Placeholder: drift monitoring (PSI/KS on feature and score distributions) ships in
// Phase 12 -- no /admin/drift endpoint exists yet (confirmed absent from
// gateway/app/routers/admin.py). Renders a real, working empty state rather than
// blocking Phase 11 on Phase 12's backend.
export default function DriftPanel() {
  return (
    <div className="rounded border border-dashed p-4 text-sm text-gray-400">
      Drift monitoring (PSI/KS on feature and score distributions) ships in Phase 12 -- no
      /admin/drift endpoint exists yet. This panel is a placeholder.
    </div>
  );
}
