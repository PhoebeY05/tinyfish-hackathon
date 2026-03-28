export default function ProgressBar({ job }) {
    const progress = job?.progress || {};
    const total = progress.total_images || 0;
    const current = progress.processed_images || 0;
    const percent = total > 0 ? Math.round((current / total) * 100) : 0;

    const stepLabels = {
        queued: 'Queued',
        extracting_zip: 'Extracting images...',
        classifying_images: 'Classifying species...',
        collecting_evidence: 'Gathering evidence...',
        building_report: 'Building report...',
        completed: 'Complete',
        failed: 'Failed',
    };

    const stepLabel = stepLabels[progress.current_step] || progress.current_step;

    return (
        <div className="space-y-4">
            {/* Status */}
            <div>
                <p className="font-serif text-lg font-bold" style={{ color: 'var(--ink)' }}>
                    {stepLabel}
                </p>
                <p className="text-sm font-mono mt-1" style={{ color: 'var(--muted)' }}>
                    {current} / {total} images processed
                </p>
            </div>

            {/* Progress Bar */}
            <div
                className="w-full h-3 border"
                style={{
                    borderColor: 'var(--border)',
                    borderWidth: '1px',
                    backgroundColor: '#fafaf8',
                }}
            >
                <div
                    className="h-full transition-all duration-300"
                    style={{
                        width: `${percent}%`,
                        backgroundColor: 'var(--accent)',
                    }}
                />
            </div>

            <p className="text-sm font-mono text-right" style={{ color: 'var(--muted)' }}>
                {percent}%
            </p>
        </div>
    );
}
