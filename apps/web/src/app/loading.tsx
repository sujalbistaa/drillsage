export default function Loading() {
  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6 px-4 py-24 md:px-8" role="status">
      <div className="flex items-center gap-4">
        <span className="h-10 w-2 animate-scan bg-brand" aria-hidden />
        <p className="melt text-4xl uppercase md:text-6xl">Tripping in&hellip;</p>
      </div>
      <p className="label text-muted-foreground">Loading reports from the field</p>
    </div>
  );
}
