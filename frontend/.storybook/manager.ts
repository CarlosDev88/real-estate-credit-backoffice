import { addons } from "storybook/manager-api";
import { create } from "storybook/theming";

// Solo el nombre: los colores del manager quedan los de Storybook (no lee los tokens).
addons.setConfig({
  theme: create({ base: "light", brandTitle: "Umbral · Design system" }),
});
