import type { StorybookConfig } from "@storybook/react-vite";
const config: StorybookConfig = {
  core: { disableTelemetry: true },
  stories: ["../src/design-system/**/*.stories.tsx"],
  framework: "@storybook/react-vite",
  addons: [],
};
export default config;
