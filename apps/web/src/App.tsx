import { useAppStore } from "./store";
import { UploadTab } from "./components/UploadTab";
import { BrowseTab } from "./components/BrowseTab";
import { WfsTab } from "./components/WfsTab";

const TABS = [
  { key: "upload", label: "Upload" },
  { key: "wfs", label: "WFS Collect" },
  { key: "browse", label: "Browse & Map" }
] as const;

export default function App() {
  const activeTab = useAppStore((s) => s.activeTab);
  const setActiveTab = useAppStore((s) => s.setActiveTab);

  return (
    <main className="app-wrap">
      <header className="hero">
        <div className="hero-top">
          <h1>Geodata Workbench</h1>
          <div className="hero-badges">
            <span>LOCAL</span>
            <span>WFS</span>
            <span>POSTGRES</span>
            <span>OSM</span>
          </div>
        </div>
        <p>로컬 업로드 즉시 변환 · WFS 수집 · 시각화를 한 화면에서</p>
      </header>

      <nav className="tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={tab.key === activeTab ? "tab active" : "tab"}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "upload" && <UploadTab />}
      {activeTab === "wfs" && <WfsTab />}
      {activeTab === "browse" && <BrowseTab />}
    </main>
  );
}
