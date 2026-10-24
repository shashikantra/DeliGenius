using System;
using System.Collections.Generic;

namespace MyCompany.Models;

public partial class State
{
    public int StateId { get; set; }

    public string? State1 { get; set; }

    public virtual ICollection<StateCountry> StateCountries { get; set; } = new List<StateCountry>();
}
