import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col items-start gap-6 px-4 py-24 md:px-8">
      <p className="label text-muted-foreground">404</p>
      <h1 className="melt melt-hover text-[clamp(3rem,12vw,9rem)] uppercase">Dry hole.</h1>
      <p className="text-lg text-muted-foreground">
        We drilled here and found nothing. The page, well or event does not exist.
      </p>
      <Link href="/" className="brutal brutal-hover label bg-brand px-5 py-3 text-brand-foreground">
        Back to the field &rarr;
      </Link>
    </div>
  );
}
