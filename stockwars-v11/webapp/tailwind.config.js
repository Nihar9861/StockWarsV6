const c = (n) => `rgb(var(--${n}) / <alpha-value>)`;
export default {content:["./index.html","./src/**/*.{ts,tsx}"],theme:{extend:{fontFamily:{sans:["Inter","system-ui","sans-serif"]},
colors:{bg:c("bg"),card:c("card"),card2:c("card2"),line:c("line"),ink:c("ink"),mute:c("mute"),up:c("up"),down:c("down"),acc:c("acc"),gold:c("gold")}}},plugins:[]}
