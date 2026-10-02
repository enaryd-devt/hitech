import { patch } from '@web/core/utils/patch';
import { useService } from '@web/core/utils/hooks';
import { useState } from '@odoo/owl';
import { computeAppsAndMenuItems } from '@web/webclient/menus/menu_helpers';

import { NavBar } from '@web/webclient/navbar/navbar';
import { AppsMenu } from "@muk_web_theme/webclient/appsmenu/appsmenu";

function containsMenu(menu, menuId) {
	return menu.id === menuId || menu.childrenTree?.some((child) => containsMenu(child, menuId));
}

patch(NavBar.prototype, {
	setup() {
        super.setup();
        this.appMenuService = useService('app_menu');
		this.appsMenuSearch = useState({ query: '' });
		this.appsMenuNavigation = useState({ activeSectionId: null });
    },
	get menuSearchResults() {
		const query = this.appsMenuSearch.query.trim().toLocaleLowerCase();
		if (!query) {
			return [];
		}
		const { apps, menuItems } = computeAppsAndMenuItems(this.menuService.getMenuAsTree('root'));
		return [...apps, ...menuItems]
			.filter((item) => `${item.label} ${item.parents || ''}`.toLocaleLowerCase().includes(query))
			.slice(0, 12);
	},
	onAppsMenuSearchInput(ev) {
		this.appsMenuSearch.query = ev.target.value;
	},
	_setActiveNavigationSection(menu) {
		if (!menu?.appID) {
			return;
		}
		const appTree = this.menuService.getMenuAsTree(menu.appID);
		const section = appTree.childrenTree?.find((item) => containsMenu(item, menu.id));
		this.appsMenuNavigation.activeSectionId = section?.id || null;
	},
	onNavBarDropdownItemSelection(menu) {
		this.appsMenuSearch.query = '';
		this._setActiveNavigationSection(menu);
		return super.onNavBarDropdownItemSelection(menu);
	},
});

patch(NavBar, {
    components: {
        ...NavBar.components,
        AppsMenu,
    },
});
