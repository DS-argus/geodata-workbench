import { create } from "zustand";

type TabName = "upload" | "convert" | "browse";

type AppStore = {
  activeTab: TabName;
  setActiveTab: (tab: TabName) => void;
};

export const useAppStore = create<AppStore>((set) => ({
  activeTab: "upload",
  setActiveTab: (tab) => set({ activeTab: tab })
}));
