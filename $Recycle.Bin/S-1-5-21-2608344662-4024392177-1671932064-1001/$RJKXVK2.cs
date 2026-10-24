using System;
using System.Collections.Generic;

namespace MyCompany.Models;

public partial class EmployeeManager
{
    public int EmployeeManagerId { get; set; }

    public int? ManagerId { get; set; }

    public int? EmployeeId { get; set; }

    public virtual Employee? Employee { get; set; }

    public virtual Manager? Manager { get; set; }
}
