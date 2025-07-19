import { create } from "zustand";
import { ThemePreset } from "@/tweakcn/types/theme";
import { defaultPresets } from "@/tweakcn/utils/theme-presets";

interface ThemePresetStore {
  presets: Record<string, ThemePreset>;
  registerPreset: (name: string, preset: ThemePreset) => void;
  unregisterPreset: (name: string) => void;
  updatePreset: (name: string, preset: ThemePreset) => void;
  getPreset: (name: string) => ThemePreset | undefined;
  getAllPresets: () => Record<string, ThemePreset>;
  unloadSavedPresets: () => void;
}

export const useThemePresetStore = create<ThemePresetStore>()((set, get) => ({
  presets: defaultPresets,
  registerPreset: (name: string, preset: ThemePreset) => {
    set((state) => ({
      presets: {
        ...state.presets,
        [name]: preset,
      },
    }));
  },
  unregisterPreset: (name: string) => {
    set((state) => {
      const { [name]: _, ...remainingPresets } = state.presets;
      return {
        presets: remainingPresets,
      };
    });
  },
  unloadSavedPresets: () => {
    set({ presets: defaultPresets });
  },
  updatePreset: (name: string, preset: ThemePreset) => {
    set((state) => ({
      presets: {
        ...state.presets,
        [name]: preset,
      },
    }));
  },
  getPreset: (name: string) => {
    return get().presets[name];
  },
  getAllPresets: () => {
    return get().presets;
  },
}));
