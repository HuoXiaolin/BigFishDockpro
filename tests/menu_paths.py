"""Find a Qt action through its user-visible menu path."""
def action_at(menu, *labels):
    for label in labels:
        action = next(item for item in menu.actions() if item.text() == label)
        menu = action.menu()
    return action
