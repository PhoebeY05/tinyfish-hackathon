export default function EvidencePanel({ evidence, tinyfishLogs = [] }) {
    return (
        <div className="space-y-2 mt-3">
            {tinyfishLogs.length > 0 ? (
                <div
                    className="p-3 border"
                    style={{
                        borderColor: 'var(--accent2)',
                        borderWidth: '1px',
                        backgroundColor: '#fefdf4',
                    }}
                >
                    <p className="font-mono text-xs font-bold uppercase mb-2" style={{ color: 'var(--accent2)' }}>
                        TinyFish Logs
                    </p>
                    <div className="space-y-1 max-h-36 overflow-y-auto">
                        {tinyfishLogs.map((line, idx) => (
                            <p key={`${idx}-${line}`} className="text-xs font-mono" style={{ color: 'var(--ink)' }}>
                                {line}
                            </p>
                        ))}
                    </div>
                </div>
            ) : null}

            {evidence.map((item, idx) => (
                <div
                    key={idx}
                    className="p-3 border text-sm"
                    style={{
                        borderColor: 'var(--border)',
                        borderWidth: '1px',
                        backgroundColor: 'var(--card)',
                    }}
                >
                    <div className="flex items-start justify-between gap-2 mb-2">
                        <p className="font-mono text-xs font-bold uppercase" style={{ color: 'var(--accent)' }}>
                            {item.source}
                        </p>
                        <div className="flex gap-1">
                            {item.supports && (
                                <span
                                    className="text-xs px-2 py-0.5 font-mono uppercase tracking-widest border"
                                    style={{
                                        backgroundColor: 'var(--success)',
                                        color: 'var(--card)',
                                        borderColor: 'var(--success)',
                                        borderWidth: '1px',
                                    }}
                                >
                                    ✓ Supports
                                </span>
                            )}
                            {item.contradicts && (
                                <span
                                    className="text-xs px-2 py-0.5 font-mono uppercase tracking-widest border"
                                    style={{
                                        backgroundColor: 'var(--danger)',
                                        color: 'var(--card)',
                                        borderColor: 'var(--danger)',
                                        borderWidth: '1px',
                                    }}
                                >
                                    ✕ Contradicts
                                </span>
                            )}
                        </div>
                    </div>
                    <p className="text-xs font-mono mb-1" style={{ color: 'var(--muted)' }}>
                        {item.type}
                    </p>
                    <p className="text-sm mb-2" style={{ color: 'var(--ink)' }}>
                        {item.extracted_claim}
                    </p>
                    {item.citation_url && (
                        <a
                            href={item.citation_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs font-mono uppercase tracking-widest inline-block"
                            style={{ color: 'var(--accent)' }}
                        >
                            View Citation ↗
                        </a>
                    )}
                </div>
            ))}
        </div>
    );
}
