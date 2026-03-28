export default function Hero() {
    return (
        <header className="header-border bg-card px-8 sm:px-10 py-5 flex items-baseline gap-4">
            <div className="font-serif text-2xl font-bold tracking-tighter">
                Avian<span className="italic text-accent">IQ</span>
            </div>
            <div className="text-xs tracking-widest uppercase text-muted border-l border-border pl-4">
                Ornithology Lab
            </div>
        </header>
    );
}
