// The split used by Login and Register. The ink panel states what the product
// does; the paper panel does the work.
import { cx, theme } from "../theme";

export default function AuthLayout({ children }) {
  return (
    <div className={theme.auth.shell}>
      <aside className={theme.auth.aside}>
        <span className="u-display text-lg leading-none text-paper">Lost&nbsp;&amp;&nbsp;Found</span>

        <div className="max-w-lg">
          <h1 className="u-display text-[clamp(3rem,6vw,4.75rem)] text-paper">
            Describe it.
            <br />
            We&rsquo;ll find it.
          </h1>
          <p className="mt-7 max-w-md text-base leading-relaxed text-white/55">
            Every item handed in at a security post is photographed. Say what you lost in
            your own words and we search those photographs directly — no categories, no
            browsing, no tags to guess.
          </p>
        </div>

        <p className="u-meta text-white/55">Campus property office</p>
      </aside>

      <div className={theme.auth.pane}>
        <div className={theme.auth.card}>{children}</div>
      </div>
    </div>
  );
}
