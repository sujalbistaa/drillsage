/** Shown when the API or the field snapshot is unavailable: say why and what to run. */
export function NoSignal({ reason }: { reason: string }) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-24 md:px-8">
      <div className="brutal bg-surface p-6 md:p-10">
        <p className="label text-danger">No signal from the rig</p>
        <h1 className="melt mt-3 text-5xl uppercase md:text-7xl">Dead air.</h1>
        <p className="mt-6 text-lg text-pretty">{reason}</p>
        <pre className="label mt-6 overflow-x-auto border bg-background p-4 leading-6 normal-case">
          {
            "make data-fetch   # once: raw Volve reports\nmake snapshot     # build the field snapshot\nmake ui           # API + web, no database needed"
          }
        </pre>
      </div>
    </div>
  );
}
