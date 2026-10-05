import { Workspace } from "./Workspace";

export default function Home() {
  return (
    <>
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto max-w-5xl px-6 py-4 text-lg font-semibold text-stone-900">Arcana</div>
      </header>
      <Workspace />
    </>
  );
}
