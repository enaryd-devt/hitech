import { Dropdown } from "@web/core/dropdown/dropdown";

/**
 * The dropdown slot is rendered by NavBar: its search state lives there.
 * Keeping this component standard also preserves Odoo's native auto-close.
 */
export class AppsMenu extends Dropdown {}
