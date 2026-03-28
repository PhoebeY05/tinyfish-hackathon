export default function ProgressBar({ job }) {
    const progress = job?.progress || {};
    const total = progress.total_images || 0;
    const current = progress.processed_images || 0;
    const percent = total > 0 ? Math.round((current / total) * 100) : 0;
    const logs = Array.isArray(progress.logs) ? progress.logs : [];
    const recentLogs = logs.slice(-12).join(' | ');

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
    const isTerminal = progress.current_step === 'completed' || progress.current_step === 'failed';
    const openaiRunning =
        !isTerminal &&
        (progress.current_step === 'classifying_images' || recentLogs.includes('OpenAI:'));
    const tinyfishRunning =
        !isTerminal &&
        (progress.current_step === 'collecting_evidence' || recentLogs.includes('TinyFish'));
    const showIndeterminate = !isTerminal && total > 0 && percent === 0;

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

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="p-3 border" style={{ borderColor: openaiRunning ? 'var(--accent)' : 'var(--border)' }}>
                    <p className="text-xs font-mono tracking-widest uppercase" style={{ color: 'var(--muted)' }}>
                        OpenAI
                    </p>
                    <p className="text-sm font-mono mt-1" style={{ color: openaiRunning ? 'var(--accent)' : 'var(--ink)' }}>
                        {openaiRunning ? 'Running classification...' : 'Idle'}
                    </p>
                </div>
                <div className="p-3 border" style={{ borderColor: tinyfishRunning ? 'var(--accent2)' : 'var(--border)' }}>
                    <p className="text-xs font-mono tracking-widest uppercase" style={{ color: 'var(--muted)' }}>
                        TinyFish
                    </p>
                    <p className="text-sm font-mono mt-1" style={{ color: tinyfishRunning ? 'var(--accent2)' : 'var(--ink)' }}>
                        {tinyfishRunning ? 'Gathering evidence...' : 'Idle'}
                    </p>
                </div>
            </div>

            {/* Progress Bar */}
            <div
                className="w-full h-3 border relative overflow-hidden"
                style={{
                    borderColor: 'var(--border)',
                    borderWidth: '1px',
                    backgroundColor: '#fafaf8',
                }}
            >
                {showIndeterminate ? (
                    <div className="progress-indeterminate" />
                ) : (
                    <div
                        className="h-full transition-all duration-300"
                        style={{
                            width: `${percent}%`,
                            backgroundColor: 'var(--accent)',
                        }}
                    />
                )}
            </div>

            <p className="text-sm font-mono text-right" style={{ color: 'var(--muted)' }}>
                {percent}%
            </p>

            <div className="border" style={{ borderColor: 'var(--border)' }}>
                <div className="px-3 py-2 border-b" style={{ borderColor: 'var(--border)', backgroundColor: '#fafaf8' }}>
                    <p className="text-xs font-mono tracking-widest uppercase" style={{ color: 'var(--muted)' }}>
                        Live Logs
                    </p>
                </div>
                <div className="p-3 max-h-56 overflow-y-auto" style={{ backgroundColor: '#fff' }}>
                    {logs.length === 0 ? (
                        <p className="text-xs font-mono" style={{ color: 'var(--muted)' }}>
                            Waiting for analysis logs...
                        </p>
                    ) : (
                        <div className="space-y-1">
                            {logs.slice(-25).map((line, idx) => (
                                <p key={`${idx}-${line}`} className="text-xs font-mono" style={{ color: 'var(--ink)' }}>
                                    {line}
                                </p>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
