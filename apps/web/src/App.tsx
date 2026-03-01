import { useAppStore } from "./store";
import { UploadTab } from "./components/UploadTab";
import { ConvertTab } from "./components/ConvertTab";
import { BrowseTab } from "./components/BrowseTab";

const TABS = [
  { key: "upload", label: "Upload" },
  { key: "convert", label: "Convert" },
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
            <span>POSTGRES</span>
            <span>OSM</span>
          </div>
        </div>
        <p>공간데이터 업로드 · 변환 · 시각화를 한 화면에서</p>
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
      {activeTab === "convert" && <ConvertTab />}
      {activeTab === "browse" && <BrowseTab />}
    </main>
  );
}
