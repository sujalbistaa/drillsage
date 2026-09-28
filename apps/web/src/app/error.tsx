"use client";

export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto flex max-w-3xl flex-col items-start gap-6 px-4 py-24 md:px-8">
      <p className="label text-danger">Unexpected error</p>
      <h1 className="melt text-[clamp(3rem,11vw,8rem)] uppercase">Well shut in.</h1>
      <p className="text-lg text-muted-foreground">
        Something broke while loading this page. Nothing was lost; try again.
      </p>
      <button
        type="button"
        onClick={reset}
        className="brutal brutal-hover label bg-brand px-5 py-3 text-brand-foreground"
      >
        Try again
      </button>
    </div>
  );
}
