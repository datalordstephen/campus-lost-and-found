// The horizontal section row. Only rendered below `md`, where the sidebar is
// tucked behind the menu button — on desktop the sidebar is the navigation and
// a second row of the same links would just be noise.
import { NavLink } from "react-router-dom";
import { SECTIONS } from "../sections";
import { cx, theme } from "../theme";

export default function SectionNav({ workspace }) {
  return (
    <nav className={cx(theme.tab.row, "md:hidden")}>
      {SECTIONS[workspace].map(({ id, label }) => (
        <NavLink
          key={id}
          to={`/${workspace}/${id}`}
          className={({ isActive }) => (isActive ? theme.tab.itemActive : theme.tab.item)}
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
