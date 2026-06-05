import type { KeyboardEvent } from "react";
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
  const activeIndex = TABS.findIndex((tab) => tab.key === activeTab);

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex = index;
    if (event.key === "ArrowRight") {
      nextIndex = (index + 1) % TABS.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + TABS.length) % TABS.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = TABS.length - 1;
    } else {
      return;
    }
    event.preventDefault();
    const nextTab = TABS[nextIndex];
    setActiveTab(nextTab.key);
    const button = document.getElementById(`tab-${nextTab.key}`);
    button?.focus();
  };

  return (
    <main className="app-wrap">
      <header className="hero">
        <div className="hero-top">
          <h1>Geodata Workbench</h1>
        </div>
      </header>

      <nav className="tabs" role="tablist" aria-label="메인 기능 탭">
        {TABS.map((tab, index) => {
          const isActive = tab.key === activeTab;
          return (
            <button
              key={tab.key}
              id={`tab-${tab.key}`}
              role="tab"
              aria-selected={isActive}
              aria-controls={`panel-${tab.key}`}
              tabIndex={isActive ? 0 : -1}
              className={isActive ? "tab active" : "tab"}
              onClick={() => setActiveTab(tab.key)}
              onKeyDown={(event) => onTabKeyDown(event, index)}
            >
              {tab.label}
            </button>
          );
        })}
      </nav>

      <section
        id={`panel-${TABS[activeIndex]?.key ?? "upload"}`}
        role="tabpanel"
        aria-labelledby={`tab-${TABS[activeIndex]?.key ?? "upload"}`}
        className="tab-panel"
      >
        {activeTab === "upload" && <UploadTab />}
        {activeTab === "wfs" && <WfsTab />}
        {activeTab === "browse" && <BrowseTab />}
      </section>
    </main>
  );
}
