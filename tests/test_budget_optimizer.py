from ai.budget_optimizer import allocate_budget


def test_budget_allocation_preserves_spendable_total():
    allocations, _ = allocate_budget(1200, {'Entertainment': 3, 'Food': 2, 'Other': 1})
    assert allocations == {'Entertainment': 600.0, 'Food': 400.0, 'Other': 200.0}
    assert sum(allocations.values()) == 1200


def test_budget_allocation_falls_back_for_new_user_without_history():
    allocations, _ = allocate_budget(1000, {'Food': 0, 'Travel': 0})
    assert round(sum(allocations.values()), 2) == 1000
    assert len(allocations) == 6
