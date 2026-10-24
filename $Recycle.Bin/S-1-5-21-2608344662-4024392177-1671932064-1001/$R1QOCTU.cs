using System;
using System.Collections.Generic;

namespace WebApplication1.Models;

public partial class Employee
{
    public int EmployeeId { get; set; }

    public string FirstName { get; set; } = null!;

    public string LastName { get; set; } = null!;

    public string Address { get; set; } = null!;

    public string City { get; set; } = null!;

    public int? ManagerId { get; set; }

    public virtual Manager? Manager { get; set; }
}
