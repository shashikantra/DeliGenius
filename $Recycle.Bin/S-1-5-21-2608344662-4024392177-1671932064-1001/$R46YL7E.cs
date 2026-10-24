using System;
using System.Collections.Generic;

namespace MyCompany.Models;

public partial class Employee
{
    public int EmployeeId { get; set; }

    public string FirstName { get; set; } = null!;

    public string LastName { get; set; } = null!;

    public string Address { get; set; } = null!;

    public string City { get; set; } = null!;

    public int? StateCountryId { get; set; }

    public int? JobTitleId { get; set; }

    public int? DepartmentId { get; set; }

    public virtual Department? Department { get; set; }

    public virtual ICollection<EmployeeManager> EmployeeManagers { get; set; } = new List<EmployeeManager>();

    public virtual JobTitle? JobTitle { get; set; }

    public virtual StateCountry? StateCountry { get; set; }
}
