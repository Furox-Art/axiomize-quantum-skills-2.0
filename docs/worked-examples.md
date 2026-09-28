# Worked Examples  
  
End-to-end examples showing modeling + reasoning together.  
  
## Example 1: Drug dosing schedule  
  
The reasoning engine explores 3 dosing strategies (fixed interval, weight-based, response-adaptive) while the modeling engine simulates each one. The weakest strategy gets eliminated by evidence, not by gut feeling.  
  
## Example 2: Supply chain under uncertainty  
  
Multiple demand scenarios stay alive in parallel. Each gets a full simulation. Only when the data clearly favors one inventory policy does the system commit.  
  
## Example 3: Epidemic threshold estimation  
  
Different R0 hypotheses compete. Bayesian updates kill off implausible values as evidence accumulates. You get a posterior distribution, not a point estimate dressed up as certainty. 
