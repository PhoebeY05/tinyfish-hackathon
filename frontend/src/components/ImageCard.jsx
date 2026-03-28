import { useState } from 'react';
import DisputeBadge from './DisputeBadge';
import EvidencePanel from './EvidencePanel';

export default function ImageCard({ image }) {
    const [expandEvidence, setExpandEvidence] = useState(false);

    const primary = image.primary_prediction;
    const alternates = image.alternate_candidates || [];
    const dispute = image.confidence_dispute || {};
    const confidencePercent = Math.round((primary.confidence || 0) * 100);
    const confidenceColor =
        primary.confidence >= 0.8 ? 'var(--success)' : primary.confidence >= 0.65 ? 'var(--accent2)' : 'var(--danger)';

    return (
        <div
            className="border overflow-hidden transition-all hover:border-accent"
            style={{
                borderColor: 'var(--border)',
                borderWidth: '1px',
                backgroundColor: 'var(--card)',
            }}
        >
            {/* Header with 3-column layout: thumbnail | metadata | confidence */}
            <div className="flex gap-4 p-4 border-b" style={{ borderColor: 'var(--border)' }}>
                {/* Thumbnail - Left Column */}
                <div
                    className="w-28 h-28 flex-shrink-0 border"
                    style={{
                        borderColor: 'var(--border)',
                        backgroundColor: '#f9f7f4',
                        backgroundImage: image.filename
                            ? `url('data:image/jpeg;base64,${image.filename.substring(0, 100)}...')`
                            : 'none',
                        backgroundSize: 'cover',
                        backgroundPosition: 'center',
                    }}
                >
                    {!image.filename && (
                        <div className="w-full h-full flex items-center justify-center text-3xl">🦅</div>
                    )}
                </div>

                {/* Metadata - Center Column */}
                <div className="flex-1 min-w-0">
                    <h3 className="font-serif font-bold text-base sm:text-lg" style={{ color: 'var(--ink)' }}>
                        {primary.common_name}
                    </h3>
                    <p className="text-xs italic text-muted mt-1">{primary.scientific_name}</p>

                    {/* Alternates */}
                    {alternates.length > 0 && (
                        <div className="mt-2">
                            <p className="text-xs font-mono uppercase tracking-widest text-muted">Also:</p>
                            <div className="flex flex-wrap gap-1 mt-1">
                                {alternates.slice(0, 2).map((alt, idx) => (
                                    <span
                                        key={idx}
                                        className="tag-default text-xs"
                                        style={{ color: 'var(--muted)' }}
                                    >
                                        {alt.common_name}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Confidence - Right Column */}
                <div className="flex flex-col items-center justify-center gap-1 flex-shrink-0">
                    <div
                        className="font-serif font-bold text-2xl"
                        style={{ color: confidenceColor }}
                    >
                        {confidencePercent}%
                    </div>
                    <div className="text-xs font-mono uppercase">Confidence</div>
                    <DisputeBadge status={dispute.status} />
                </div>
            </div>

            {/* Body - 2 Column Layout */}
            <div className="p-4 space-y-4">
                {/* Confidence Bar */}
                <div className="space-y-1">
                    <p className="text-xs font-mono uppercase tracking-widest text-muted">Confidence</p>
                    <div
                        className="h-2 border"
                        style={{ borderColor: 'var(--border)', backgroundColor: '#fafaf8' }}
                    >
                        <div
                            className="h-full transition-all"
                            style={{
                                width: `${confidencePercent}%`,
                                backgroundColor: confidenceColor,
                            }}
                        />
                    </div>
                </div>

                {/* Location Context */}
                <div
                    className="p-3 border"
                    style={{
                        borderColor: 'var(--accent)',
                        borderWidth: '1px',
                        backgroundColor: '#f9fdf7',
                    }}
                >
                    <p className="text-xs font-mono uppercase tracking-widest" style={{ color: 'var(--accent)' }}>
                        Recent Sighting
                    </p>
                    <p className="text-sm mt-1" style={{ color: 'var(--ink)' }}>
                        {image.location_context?.last_spotted_text || 'No recent sightings recorded'}
                    </p>
                </div>

                {/* Evidence Toggle */}
                <button
                    onClick={() => setExpandEvidence(!expandEvidence)}
                    className="w-full text-left px-3 py-2 font-mono text-xs tracking-widest uppercase transition border"
                    style={{
                        borderColor: expandEvidence ? 'var(--accent)' : 'var(--border)',
                        backgroundColor: expandEvidence ? '#f9fdf7' : 'var(--card)',
                        color: expandEvidence ? 'var(--accent)' : 'var(--ink)',
                    }}
                >
                    {expandEvidence ? '▼' : '▶'} Evidence ({image.evidence?.length || 0})
                </button>

                {/* Evidence Panel */}
                {expandEvidence && <EvidencePanel evidence={image.evidence || []} />}

                {/* Dispute Box */}
                {dispute.status !== 'no_dispute' && (
                    <div
                        className="p-3 border"
                        style={{
                            borderColor: 'var(--accent2)',
                            borderWidth: '1px',
                            backgroundColor: '#fefdf4',
                        }}
                    >
                        <p className="text-xs font-mono uppercase tracking-widest" style={{ color: 'var(--accent2)' }}>
                            {dispute.status === 'major_disagreement' ? '⚠ Major Dispute' : '◐ Minor Concern'}
                        </p>
                        <p className="text-sm mt-1" style={{ color: 'var(--ink)' }}>
                            {dispute.reason}
                        </p>
                    </div>
                )}

                {/* Review Status */}
                <div className="text-xs font-mono uppercase tracking-widest text-muted">
                    Review: <span style={{ color: 'var(--accent)' }}>{image.review_status}</span>
                </div>
            </div>
        </div>
    );
}
