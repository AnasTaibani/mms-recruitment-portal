// MMS brand palette for charts and inline styles (mirrors the CSS / Tailwind tokens).
export const BRAND = { sky: "#A0D5FC", blue: "#67B5F4", royal: "#4089DE", deep: "#2265C8", pale: "#EDF5FE" };
export const NEUTRAL = { white: "#FFFFFF", canvas: "#F7F8FA", line: "#E8EBEF", ink: "#20242B", subtle: "#737B87", grey: "#AEB5BF", soft: "#D5DBE3" };
export const STATUS = { positive: "#3E8E63", negative: "#C0504D", warning: "#C08A2E" };
// series order: primary → secondary → supporting → neutral
export const SERIES_COLORS = [BRAND.deep, BRAND.royal, BRAND.blue, BRAND.sky, NEUTRAL.grey, STATUS.positive, STATUS.warning, NEUTRAL.soft];
export const AXIS = { fontSize: 12, fill: NEUTRAL.subtle, fontFamily: "IBM Plex Sans, system-ui, sans-serif" };
