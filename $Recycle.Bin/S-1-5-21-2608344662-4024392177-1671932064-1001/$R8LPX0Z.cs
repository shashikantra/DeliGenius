using System;
using System.Collections.Generic;

namespace MyCompany.Models;

public partial class StateCountry
{
    public int StateCountryId { get; set; }

    public int? StateId { get; set; }

    public int? CountryId { get; set; }

    public virtual Country? Country { get; set; }

    public virtual ICollection<Employee> Employees { get; set; } = new List<Employee>();

    public virtual State? State { get; set; }
}
