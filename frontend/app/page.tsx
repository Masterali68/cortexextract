import { Header } from "@/components/Header";
import { ControlPanel } from "@/components/ControlPanel";
import { StudioWorkspace } from "@/components/StudioWorkspace";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-canvas text-zinc-100">
      <Header />
      <main className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col gap-4 p-6">
        <ControlPanel />
        <StudioWorkspace />
      </main>
    </div>
  );
}