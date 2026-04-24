import operator

def evaluate_condition(value, op_str, threshold):
    ops = {
        '>': operator.gt,
        '<': operator.lt,
        '>=': operator.ge,
        '<=': operator.le,
        '==': operator.eq,
        '!=': operator.ne
    }
    op_func = ops.get(op_str)
    if not op_func:
        raise ValueError(f"Unknown operator {op_str}")
    return op_func(value, threshold)

def check_rule(rule, primary_value, shunt_value=None):
    """
    Checks if the immediate condition of the rule is met.
    Does not evaluate duration.
    """
    # Evaluate primary condition
    primary_met = evaluate_condition(primary_value, rule['operator'], rule['threshold'])
    
    if rule['type'] == 'CONDITIONAL':
        # Need shunt value
        if shunt_value is None:
            return False # Shunt data missing
        shunt_met = evaluate_condition(shunt_value, rule['shunt_operator'], rule['shunt_threshold'])
        return primary_met and shunt_met
        
    return primary_met
