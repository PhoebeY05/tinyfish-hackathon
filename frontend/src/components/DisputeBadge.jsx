export default function DisputeBadge({ status }) {
    let bgColor = 'var(--success)';
    let textColor = 'var(--card)';
    let label = '✓ No Dispute';

    if (status === 'minor_disagreement') {
        bgColor = 'var(--accent2)';
        label = '◐ Minor Concern';
    } else if (status === 'major_disagreement') {
        bgColor = 'var(--danger)';
        textColor = 'var(--card)';
        label = '⚠ Major Dispute';
    }

    return (
        <span
            className="inline-block px-2.5 py-1 text-xs font-bold font-mono uppercase tracking-widest border"
            style={{
                backgroundColor: bgColor,
                color: textColor,
                borderColor: bgColor,
                borderWidth: '1px',
            }}
        >
            {label}
        </span>
    );
}
